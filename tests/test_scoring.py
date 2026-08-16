from fantasy_draft_analyst.models import DraftContext
from fantasy_draft_analyst.scoring import (
    component_scores,
    estimate_player_points,
    market_ppg_prior,
    normalize_adp,
    score_candidates,
    weighted_preseason_score,
    survival_probability,
)

from .fixtures import sample_draft, sample_picks, sample_players


def test_scores_exclude_picked_players_and_penalize_out_players():
    ctx = DraftContext(draft=sample_draft(), picks=sample_picks(), players=sample_players(), my_slot=2)
    candidates = score_candidates(ctx)
    names = [candidate.name for candidate in candidates]
    assert "Bijan Robinson" not in names
    assert candidates[0].name != "Hurt Runner"
    assert candidates[0].score > candidates[-1].score


def test_survival_probability_drops_when_adp_is_before_next_pick():
    assert survival_probability(10, next_pick_after_current=25, current_pick=5) < 0.3
    assert survival_probability(60, next_pick_after_current=25, current_pick=5) > 0.9


def test_committee_rb_with_limited_history_is_capped():
    woody_marks_profile = {
        "full_name": "Woody Marks",
        "position": "RB",
        "team": "HOU",
        "search_rank": 105,
        "years_exp": 1,
        "depth_chart_order": 2,
        "active": True,
    }
    points, fpg, _, factors = estimate_player_points(woody_marks_profile, "RB", 105, "ppr")
    assert fpg == 10.8
    assert points == 172.8
    assert any("limited last-two-year" in factor for factor in factors)


def test_veteran_rb2_is_capped_by_role_gate():
    allgeier_like_profile = {
        "full_name": "Tyler Allgeier",
        "position": "RB",
        "team": "ARI",
        "search_rank": 89,
        "years_exp": 4,
        "depth_chart_order": 2,
        "active": True,
    }
    points, fpg, _, factors = estimate_player_points(allgeier_like_profile, "RB", 89, "ppr")
    assert fpg == 12.5
    assert points == 200
    assert "RB2 committee role cap" in factors


def test_preseason_gate_uses_schedule_as_light_modifier():
    base = {
        "role": 80,
        "talent": 80,
        "team_environment": 80,
        "ceiling": 80,
        "schedule": 20,
        "risk": 20,
    }
    great_schedule = {**base, "schedule": 100}
    assert weighted_preseason_score(great_schedule) - weighted_preseason_score(base) == 4.0


def test_component_scores_penalize_committee_role_even_with_good_rank():
    player = {
        "full_name": "Woody Marks",
        "position": "RB",
        "team": "HOU",
        "search_rank": 105,
        "years_exp": 1,
        "depth_chart_order": 2,
    }
    components = component_scores(
        player,
        "RB",
        105,
        points=172.8,
        fpg=10.8,
        floor=133.9,
        ceiling=211.7,
        risk=0.08,
        opportunity=0.7,
        team_context=0.65,
        schedule_context=0.55,
        scarcity=0.4,
    )
    assert components["role"] < 75
    assert components["talent"] < 60
    assert round(components["schedule"], 2) == 55


def test_normalize_adp_does_not_use_fantasy_data_id_as_rank():
    player = {"fantasy_data_id": 18890, "search_rank": 18}
    assert normalize_adp(player, 350) == 18


def test_elite_market_qb_gets_strong_role_and_talent_prior():
    player = {
        "full_name": "Josh Allen",
        "position": "QB",
        "team": "BUF",
        "search_rank": 18,
        "years_exp": 8,
        "active": True,
    }
    points, fpg, volatility, _ = estimate_player_points(player, "QB", 18, "ppr")
    components = component_scores(
        player,
        "QB",
        18,
        points=points,
        fpg=fpg,
        floor=points - volatility / 2,
        ceiling=points + volatility / 2,
        risk=0.08,
        opportunity=0.55,
        team_context=0.65,
        schedule_context=0.55,
        scarcity=0.2,
    )
    assert components["role"] >= 80
    assert components["talent"] >= 90


def test_elite_rb_market_curve_is_not_flat():
    ppgs = [market_ppg_prior("RB", rank, "ppr") for rank in [1, 2, 6, 12, 24]]
    assert len(set(round(ppg, 2) for ppg in ppgs)) == len(ppgs)
    assert ppgs == sorted(ppgs, reverse=True)

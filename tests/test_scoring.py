from fantasy_draft_analyst.models import DraftContext
from fantasy_draft_analyst.scoring import (
    component_scores,
    draft_strategy_modifiers,
    estimate_player_points,
    market_ppg_prior,
    normalize_adp,
    roster_strategy_summary,
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
        "depth_chart_order": 1,
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
    assert components["talent"] >= 70


def test_elite_rb_market_curve_is_not_flat():
    ppgs = [market_ppg_prior("RB", rank, "ppr") for rank in [1, 2, 6, 12, 24]]
    assert len(set(round(ppg, 2) for ppg in ppgs)) == len(ppgs)
    assert ppgs == sorted(ppgs, reverse=True)


def test_top_qb_components_are_not_flat():
    rows = []
    for name, team, rank in [("Josh Allen", "BUF", 4), ("Joe Burrow", "CIN", 14), ("Jalen Hurts", "PHI", 30)]:
        player = {"full_name": name, "position": "QB", "team": team, "search_rank": rank, "depth_chart_order": 1, "years_exp": 6}
        points, fpg, volatility, _ = estimate_player_points(player, "QB", rank, "ppr")
        rows.append(component_scores(player, "QB", rank, points, fpg, points - volatility / 2, points + volatility / 2, 0.08, 0.55, 0.65, 0.55, 0.2))
    assert len({round(row["role"], 2) for row in rows}) > 1
    assert len({round(row["talent"], 2) for row in rows}) > 1
    assert len({round(row["team_environment"], 2) for row in rows}) > 1


def test_top_wr_te_components_are_not_flat():
    players = [
        {"full_name": "Ja'Marr Chase", "position": "WR", "team": "CIN", "search_rank": 3, "depth_chart_order": 1, "years_exp": 5},
        {"full_name": "CeeDee Lamb", "position": "WR", "team": "DAL", "search_rank": 9, "depth_chart_order": 1, "years_exp": 6},
        {"full_name": "Trey McBride", "position": "TE", "team": "ARI", "search_rank": 19, "depth_chart_order": 1, "years_exp": 4},
        {"full_name": "Brock Bowers", "position": "TE", "team": "LV", "search_rank": 22, "depth_chart_order": 1, "years_exp": 2},
    ]
    rows = []
    for player in players:
        position = player["position"]
        rank = player["search_rank"]
        points, fpg, volatility, _ = estimate_player_points(player, position, rank, "ppr")
        rows.append(component_scores(player, position, rank, points, fpg, points - volatility / 2, points + volatility / 2, 0.08, 0.7, 0.65, 0.55, 0.2))
    assert len({round(row["role"], 2) for row in rows}) > 1
    assert len({round(row["team_environment"], 2) for row in rows}) > 1


def test_strategy_waits_on_qb_in_early_one_qb_ppr():
    ctx = DraftContext(draft=sample_draft(), picks=sample_picks(), players=sample_players(), my_slot=2)
    modifiers, factors = draft_strategy_modifiers(
        ctx,
        "QB",
        adp=18,
        vbd=80,
        scarcity=0.2,
        survival=0.8,
        roster_fit=1.0,
    )
    assert modifiers["strategy_wait_on_qb"] < 0
    assert any("waits on QB" in factor for factor in factors)


def test_strategy_boosts_early_rb_wr_anchor_core():
    ctx = DraftContext(draft=sample_draft(), picks=sample_picks(), players=sample_players(), my_slot=2)
    modifiers, factors = draft_strategy_modifiers(
        ctx,
        "WR",
        adp=20,
        vbd=70,
        scarcity=0.5,
        survival=0.1,
        roster_fit=1.0,
    )
    assert modifiers["strategy_anchor_core"] > 0
    assert any("RB/WR anchors" in factor for factor in factors)


def test_strategy_blocks_kicker_before_final_rounds():
    ctx = DraftContext(draft=sample_draft(), picks=sample_picks(), players=sample_players(), my_slot=2)
    modifiers, factors = draft_strategy_modifiers(
        ctx,
        "K",
        adp=175,
        vbd=0,
        scarcity=0.1,
        survival=0.95,
        roster_fit=0.25,
    )
    assert modifiers["strategy_stream_k_def_late"] < -20
    assert any("draft them last" in factor for factor in factors)


def test_reasoning_strategy_summary_exposes_live_rules():
    ctx = DraftContext(draft=sample_draft(), picks=sample_picks(), players=sample_players(), my_slot=2)
    summary = roster_strategy_summary(ctx)
    assert summary["format"] == "4-team 1-QB PPR redraft strategy"
    assert "Use ADP as market price, not as the ranking." in summary["rules"]

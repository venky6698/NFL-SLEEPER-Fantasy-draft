from fantasy_draft_analyst.models import DraftContext
from fantasy_draft_analyst.scoring import score_candidates, survival_probability

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

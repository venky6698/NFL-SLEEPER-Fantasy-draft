from fantasy_draft_analyst.models import Candidate
from fantasy_draft_analyst.weekly import weekly_projection


def candidate():
    return Candidate(
        player_id="1",
        name="Test Runner",
        position="RB",
        team="HOU",
        age=25,
        adp=100,
        projected_season_points=170,
        projected_fp_per_game=10,
        floor=120,
        ceiling=210,
        vbd=0,
        scarcity=0.2,
        roster_fit=0.5,
        survival_probability=0.5,
        risk=0.1,
        opportunity=0.7,
        team_context=0.65,
        schedule_context=0.55,
        score=70,
        major_factors=[],
        source_quality=[],
    )


def test_weekly_projection_normalizes_to_season_points():
    schedule = [
        {"week": week, "opponent": {"abbreviation": "TEN"}, "is_home": week % 2 == 0}
        for week in range(1, 18)
    ]
    rows = weekly_projection(candidate(), schedule, {})
    assert len(rows) == 17
    assert round(sum(row["projected_ppr"] for row in rows), 1) == 170.0

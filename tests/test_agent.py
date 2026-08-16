from fantasy_draft_analyst.agent import DraftAnalyst, enforce_available_recommendation
from fantasy_draft_analyst.config import Settings
from fantasy_draft_analyst.models import Candidate

from .fixtures import sample_draft, sample_picks, sample_players


class FakeSleeper:
    def draft(self, draft_id):
        return sample_draft()

    def draft_picks(self, draft_id):
        return sample_picks()

    def players(self):
        return sample_players()

    def traded_picks(self, draft_id):
        return []

    def league(self, league_id):
        return {"league_id": league_id}

    def rosters(self, league_id):
        return []

    def users(self, league_id):
        return []


class FakeMcp:
    def call_if_available(self, name, arguments=None):
        if name == "recommend_draft_pick":
            return {"recommendation": "MCP baseline"}
        return None


def test_recommend_returns_top_three_without_external_services(monkeypatch):
    settings = Settings(sleeper_draft_id="mock-draft", my_draft_slot=2, ollama_url="http://127.0.0.1:9")
    analyst = DraftAnalyst(settings, sleeper=FakeSleeper(), mcp=FakeMcp())
    result = analyst.recommend()
    assert result["draft"]["pick_no"] == 2
    assert len(result["top_3"]) == 3
    assert result["llm_recommendation"]["final_recommendation"]
    assert result["provider"] == "local"


def test_enforce_available_recommendation_overrides_drafted_player():
    candidates = [
        Candidate(
            player_id="8150",
            name="Kyren Williams",
            position="RB",
            team="LAR",
            age=26,
            adp=25,
            projected_season_points=300,
            projected_fp_per_game=18,
            floor=220,
            ceiling=370,
            vbd=50,
            scarcity=0.5,
            roster_fit=1,
            survival_probability=0.05,
            risk=0.1,
            opportunity=0.8,
            team_context=0.7,
            schedule_context=0.6,
            score=150,
            major_factors=["RB value over replacement 50.0"],
            source_quality=["test"],
        )
    ]
    parsed = {"final_recommendation": "Bijan Robinson", "top_3": [{"player_id": "9509", "name": "Bijan Robinson"}]}
    guarded = enforce_available_recommendation(parsed, candidates)
    assert guarded["final_recommendation"].startswith("Kyren Williams")
    assert guarded["availability_override"]
    assert guarded["top_3"][0]["player_id"] == "8150"


def test_enforce_available_recommendation_normalizes_llm_list_response():
    candidates = [
        Candidate(
            player_id="8150",
            name="Kyren Williams",
            position="RB",
            team="LAR",
            age=26,
            adp=25,
            projected_season_points=300,
            projected_fp_per_game=18,
            floor=220,
            ceiling=370,
            vbd=50,
            scarcity=0.5,
            roster_fit=1,
            survival_probability=0.05,
            risk=0.1,
            opportunity=0.8,
            team_context=0.7,
            schedule_context=0.6,
            score=150,
            major_factors=["RB value over replacement 50.0"],
            source_quality=["test"],
        )
    ]
    guarded = enforce_available_recommendation([{"player_id": "8150", "name": "Kyren Williams"}], candidates)
    assert guarded["final_recommendation"] == "Kyren Williams"
    assert guarded["top_3"][0]["player_id"] == "8150"


def test_enforce_available_recommendation_fills_missing_final():
    candidates = [
        Candidate(
            player_id="8150",
            name="Kyren Williams",
            position="RB",
            team="LAR",
            age=26,
            adp=25,
            projected_season_points=300,
            projected_fp_per_game=18,
            floor=220,
            ceiling=370,
            vbd=50,
            scarcity=0.5,
            roster_fit=1,
            survival_probability=0.05,
            risk=0.1,
            opportunity=0.8,
            team_context=0.7,
            schedule_context=0.6,
            score=150,
            major_factors=["RB value over replacement 50.0"],
            source_quality=["test"],
        )
    ]
    guarded = enforce_available_recommendation({"top_3": []}, candidates)
    assert guarded["final_recommendation"].startswith("Kyren Williams")
    assert "omitted" in guarded["availability_override"]


def test_enforce_available_recommendation_expands_id_only_final():
    candidates = [
        Candidate(
            player_id="8150",
            name="Kyren Williams",
            position="RB",
            team="LAR",
            age=26,
            adp=25,
            projected_season_points=300,
            projected_fp_per_game=18,
            floor=220,
            ceiling=370,
            vbd=50,
            scarcity=0.5,
            roster_fit=1,
            survival_probability=0.05,
            risk=0.1,
            opportunity=0.8,
            team_context=0.7,
            schedule_context=0.6,
            score=150,
            major_factors=["RB value over replacement 50.0"],
            source_quality=["test"],
        )
    ]
    guarded = enforce_available_recommendation({"final_recommendation": "8150"}, candidates)
    assert guarded["final_recommendation"] == "Kyren Williams (RB, LAR)"

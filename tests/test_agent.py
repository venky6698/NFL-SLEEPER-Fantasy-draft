from fantasy_draft_analyst.agent import DraftAnalyst
from fantasy_draft_analyst.config import Settings

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

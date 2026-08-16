from fantasy_draft_analyst.config import Settings
from fantasy_draft_analyst.live_sync import LiveDraftSync

from .fixtures import sample_draft, sample_picks, sample_players


class FakeSleeper:
    def draft(self, draft_id):
        return sample_draft()

    def draft_picks(self, draft_id):
        return sample_picks()

    def players(self):
        return sample_players()


def test_live_sync_snapshot_tracks_drafted_ids_and_board_rows():
    sync = LiveDraftSync(Settings(sleeper_draft_id="mock-draft"), sleeper=FakeSleeper())
    snapshot = sync.refresh()
    state = snapshot.as_dict()
    assert state["draft_id"] == "mock-draft"
    assert state["current_pick_no"] == 2
    assert "1" in state["drafted_player_ids"]
    assert state["board"][0]["name"] == "Bijan Robinson"

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .http_json import request_json, url_join


SLEEPER_BASE = "https://api.sleeper.app/v1"


@dataclass
class SleeperClient:
    base_url: str = SLEEPER_BASE

    def get(self, path: str) -> Any:
        return request_json("GET", url_join(self.base_url, path), timeout=25)

    def draft(self, draft_id: str) -> dict[str, Any]:
        return self.get(f"/draft/{draft_id}")

    def draft_picks(self, draft_id: str) -> list[dict[str, Any]]:
        return self.get(f"/draft/{draft_id}/picks")

    def traded_picks(self, draft_id: str) -> list[dict[str, Any]]:
        return self.get(f"/draft/{draft_id}/traded_picks")

    def players(self) -> dict[str, dict[str, Any]]:
        return self.get("/players/nfl")

    def league(self, league_id: str) -> dict[str, Any]:
        return self.get(f"/league/{league_id}")

    def rosters(self, league_id: str) -> list[dict[str, Any]]:
        return self.get(f"/league/{league_id}/rosters")

    def users(self, league_id: str) -> list[dict[str, Any]]:
        return self.get(f"/league/{league_id}/users")

    def league_drafts(self, league_id: str) -> list[dict[str, Any]]:
        return self.get(f"/league/{league_id}/drafts")

    def user(self, username: str) -> dict[str, Any]:
        return self.get(f"/user/{username}")

    def user_leagues(self, user_id: str, season: str = "2026") -> list[dict[str, Any]]:
        return self.get(f"/user/{user_id}/leagues/nfl/{season}")

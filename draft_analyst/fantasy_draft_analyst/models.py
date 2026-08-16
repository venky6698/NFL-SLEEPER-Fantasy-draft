from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}


@dataclass
class DraftContext:
    draft: dict[str, Any]
    picks: list[dict[str, Any]]
    players: dict[str, dict[str, Any]]
    my_slot: int
    league: dict[str, Any] | None = None
    rosters: list[dict[str, Any]] = field(default_factory=list)
    users: list[dict[str, Any]] = field(default_factory=list)
    traded_picks: list[dict[str, Any]] = field(default_factory=list)
    mcp_data: dict[str, Any] = field(default_factory=dict)
    manual_notes: dict[str, Any] = field(default_factory=dict)

    @property
    def teams(self) -> int:
        settings = self.draft.get("settings", {})
        return int(settings.get("teams") or settings.get("num_teams") or 12)

    @property
    def rounds(self) -> int:
        return int(self.draft.get("settings", {}).get("rounds") or 16)

    @property
    def scoring_type(self) -> str:
        metadata = self.draft.get("metadata", {})
        return str(metadata.get("scoring_type") or metadata.get("scoring") or "ppr").lower()

    @property
    def current_pick_no(self) -> int:
        return len(self.picks) + 1

    @property
    def picked_player_ids(self) -> set[str]:
        return {str(pick.get("player_id")) for pick in self.picks if pick.get("player_id")}


@dataclass
class Candidate:
    player_id: str
    name: str
    position: str
    team: str | None
    age: float | None
    adp: float
    projected_season_points: float
    projected_fp_per_game: float
    floor: float
    ceiling: float
    vbd: float
    scarcity: float
    roster_fit: float
    survival_probability: float
    risk: float
    opportunity: float
    team_context: float
    schedule_context: float
    score: float
    major_factors: list[str]
    source_quality: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "position": self.position,
            "team": self.team,
            "age": self.age,
            "adp": round(self.adp, 1),
            "projected_season_points": round(self.projected_season_points, 1),
            "projected_fp_per_game": round(self.projected_fp_per_game, 2),
            "floor": round(self.floor, 1),
            "ceiling": round(self.ceiling, 1),
            "vbd": round(self.vbd, 1),
            "scarcity": round(self.scarcity, 2),
            "roster_fit": round(self.roster_fit, 2),
            "survival_probability": round(self.survival_probability, 2),
            "risk": round(self.risk, 2),
            "opportunity": round(self.opportunity, 2),
            "team_context": round(self.team_context, 2),
            "schedule_context": round(self.schedule_context, 2),
            "score": round(self.score, 2),
            "major_factors": self.major_factors,
            "source_quality": self.source_quality,
        }

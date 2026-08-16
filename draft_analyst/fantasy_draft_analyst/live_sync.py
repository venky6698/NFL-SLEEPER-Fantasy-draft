from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .sleeper import SleeperClient


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LiveDraftSnapshot:
    draft_id: str
    draft: dict[str, Any]
    picks: list[dict[str, Any]]
    players: dict[str, dict[str, Any]]
    synced_at: str
    error: str | None = None

    @property
    def picked_player_ids(self) -> set[str]:
        return {str(pick.get("player_id")) for pick in self.picks if pick.get("player_id")}

    @property
    def current_pick_no(self) -> int:
        return len(self.picks) + 1

    def board_rows(self) -> list[dict[str, Any]]:
        rows = []
        teams = int((self.draft.get("settings") or {}).get("teams") or 12)
        for pick in self.picks:
            player_id = str(pick.get("player_id") or "")
            player = self.players.get(player_id) or {}
            meta = pick.get("metadata") or {}
            pick_no = int(pick.get("pick_no") or len(rows) + 1)
            rows.append(
                {
                    "pick_no": pick_no,
                    "round": int(pick.get("round") or ((pick_no - 1) // teams) + 1),
                    "draft_slot": pick.get("draft_slot"),
                    "player_id": player_id,
                    "name": player.get("full_name")
                    or f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
                    or player_id,
                    "position": player.get("position") or meta.get("position"),
                    "team": player.get("team") or meta.get("team"),
                    "is_keeper": bool(pick.get("is_keeper")),
                }
            )
        return rows

    def as_dict(self) -> dict[str, Any]:
        last = self.board_rows()[-1] if self.picks else None
        return {
            "draft_id": self.draft_id,
            "synced_at": self.synced_at,
            "error": self.error,
            "status": self.draft.get("status"),
            "current_pick_no": self.current_pick_no,
            "picked_count": len(self.picks),
            "drafted_player_ids": sorted(self.picked_player_ids),
            "last_pick": last,
            "board": self.board_rows(),
        }


@dataclass
class LiveDraftSync:
    settings: Settings
    sleeper: SleeperClient = field(default_factory=SleeperClient)
    _snapshot: LiveDraftSnapshot | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.refresh()
        self._thread = threading.Thread(target=self._run, name="live-draft-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        interval = max(5, int(self.settings.live_sync_interval_seconds))
        while not self._stop.wait(interval):
            self.refresh()

    def refresh(self) -> LiveDraftSnapshot:
        draft_id = self.settings.sleeper_draft_id
        if not draft_id:
            raise ValueError("SLEEPER_DRAFT_ID is required for live sync.")
        try:
            draft = self.sleeper.draft(draft_id)
            picks = self.sleeper.draft_picks(draft_id)
            players = self.sleeper.players()
            snapshot = LiveDraftSnapshot(
                draft_id=draft_id,
                draft=draft,
                picks=picks,
                players={str(k): v for k, v in players.items()},
                synced_at=now_iso(),
            )
        except Exception as exc:
            with self._lock:
                previous = self._snapshot
            if previous:
                snapshot = LiveDraftSnapshot(
                    draft_id=previous.draft_id,
                    draft=previous.draft,
                    picks=previous.picks,
                    players=previous.players,
                    synced_at=previous.synced_at,
                    error=str(exc),
                )
            else:
                snapshot = LiveDraftSnapshot(
                    draft_id=draft_id,
                    draft={},
                    picks=[],
                    players={},
                    synced_at=now_iso(),
                    error=str(exc),
                )
        with self._lock:
            self._snapshot = snapshot
        return snapshot

    def snapshot(self, *, force: bool = False) -> LiveDraftSnapshot:
        if force:
            return self.refresh()
        with self._lock:
            snapshot = self._snapshot
        return snapshot if snapshot else self.refresh()

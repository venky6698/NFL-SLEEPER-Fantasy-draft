from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings
from .http_json import HttpError, request_json, url_join
from .mcp_client import McpClient
from .models import DraftContext
from .reasoning import ReasoningResult, choose_reasoning
from .scoring import score_candidates
from .sleeper import SleeperClient


@dataclass
class DraftAnalyst:
    settings: Settings
    sleeper: SleeperClient | None = None
    mcp: McpClient | None = None

    def __post_init__(self) -> None:
        self.sleeper = self.sleeper or SleeperClient()
        self.mcp = self.mcp or McpClient(self.settings.nfl_mcp_url)

    def health(self) -> dict[str, Any]:
        status: dict[str, Any] = {"analyst": "ok"}
        try:
            base = self.settings.nfl_mcp_url.split("/mcp", 1)[0]
            status["nfl_mcp_health"] = request_json("GET", url_join(base, "/health"), timeout=5)
        except Exception as exc:
            status["nfl_mcp_health_error"] = str(exc)
        try:
            status["nfl_mcp_tools"] = [tool.get("name") for tool in self.mcp.list_tools().get("tools", [])][:20]
        except Exception as exc:
            status["nfl_mcp_tools_error"] = str(exc)
        try:
            status["ollama"] = request_json("GET", url_join(self.settings.ollama_url, "/api/tags"), timeout=4)
        except Exception as exc:
            status["ollama_error"] = str(exc)
        status["abacus_configured"] = bool(self.settings.abacus_api_key)
        return status

    def discover_draft_id(self) -> str:
        if self.settings.sleeper_draft_id:
            return self.settings.sleeper_draft_id
        if self.settings.sleeper_league_id:
            drafts = self.sleeper.league_drafts(self.settings.sleeper_league_id)
            if drafts:
                return str(drafts[0]["draft_id"])
        if self.settings.sleeper_username:
            user = self.sleeper.user(self.settings.sleeper_username)
            for season in ["2026", "2025"]:
                leagues = self.sleeper.user_leagues(user["user_id"], season)
                for league in leagues:
                    drafts = self.sleeper.league_drafts(league["league_id"])
                    if drafts:
                        return str(drafts[0]["draft_id"])
        raise ValueError("Set SLEEPER_DRAFT_ID, or SLEEPER_LEAGUE_ID/SLEEPER_USERNAME for discovery.")

    def infer_my_slot(self, draft: dict[str, Any]) -> int:
        if self.settings.my_draft_slot:
            return self.settings.my_draft_slot
        if self.settings.sleeper_username:
            user = self.sleeper.user(self.settings.sleeper_username)
            draft_order = draft.get("draft_order") or {}
            slot = draft_order.get(user.get("user_id"))
            if slot:
                return int(slot)
        raise ValueError("Set MY_DRAFT_SLOT or SLEEPER_USERNAME so your draft position can be inferred.")

    def build_context(self, manual_state_path: str | None = None) -> DraftContext:
        manual_notes: dict[str, Any] = {}
        if manual_state_path:
            manual_notes = json.loads(Path(manual_state_path).read_text())

        draft_id = str(manual_notes.get("draft_id") or self.discover_draft_id())
        draft = manual_notes.get("draft") or self.sleeper.draft(draft_id)
        picks = manual_notes.get("picks") or self.sleeper.draft_picks(draft_id)
        players = manual_notes.get("players") or self.sleeper.players()
        my_slot = int(manual_notes.get("my_slot") or self.infer_my_slot(draft))

        league = None
        rosters: list[dict[str, Any]] = []
        users: list[dict[str, Any]] = []
        traded_picks: list[dict[str, Any]] = []
        league_id = draft.get("league_id") or self.settings.sleeper_league_id
        if league_id:
            try:
                league = self.sleeper.league(str(league_id))
                rosters = self.sleeper.rosters(str(league_id))
                users = self.sleeper.users(str(league_id))
            except Exception:
                pass
        try:
            traded_picks = self.sleeper.traded_picks(draft_id)
        except Exception:
            traded_picks = []

        ctx = DraftContext(
            draft=draft,
            picks=picks,
            players={str(k): v for k, v in players.items()},
            my_slot=my_slot,
            league=league,
            rosters=rosters,
            users=users,
            traded_picks=traded_picks,
            manual_notes=manual_notes,
        )
        ctx.mcp_data = self.collect_mcp_context(ctx)
        return ctx

    def collect_mcp_context(self, ctx: DraftContext) -> dict[str, Any]:
        data: dict[str, Any] = {}
        draft_id = ctx.draft.get("draft_id")
        league_id = ctx.draft.get("league_id")
        tool_calls = [
            ("recommend_draft_pick", {"draft_id": draft_id, "my_slot": ctx.my_slot}),
            ("get_draft_board", {"draft_id": draft_id}),
            ("get_draft", {"draft_id": draft_id}),
            ("get_draft_picks", {"draft_id": draft_id}),
            ("get_draft_traded_picks", {"draft_id": draft_id}),
            ("get_injury_report", {}),
            ("get_high_confidence_injuries", {}),
            ("get_strength_of_schedule", {}),
            ("get_defense_rankings", {}),
            ("get_all_coaching_staffs", {}),
        ]
        if league_id:
            tool_calls.extend(
                [
                    ("get_league", {"league_id": league_id}),
                    ("get_rosters", {"league_id": league_id}),
                    ("get_league_users", {"league_id": league_id}),
                    ("get_fantasy_context", {"league_id": league_id}),
                ]
            )
        if self.settings.enable_vegas:
            tool_calls.append(("get_vegas_lines", {}))

        for name, args in tool_calls:
            if not all(value is not None for value in args.values()):
                continue
            value = self.mcp.call_if_available(name, args)
            if value is not None:
                data[name] = value
        return data

    def recommend(self, manual_state_path: str | None = None) -> dict[str, Any]:
        ctx = self.build_context(manual_state_path)
        candidates = score_candidates(ctx)
        reasoning: ReasoningResult = choose_reasoning(self.settings, ctx, candidates)
        return {
            "provider": reasoning.provider,
            "reasoning_error": reasoning.error,
            "draft": {
                "draft_id": ctx.draft.get("draft_id"),
                "status": ctx.draft.get("status"),
                "pick_no": ctx.current_pick_no,
                "my_slot": ctx.my_slot,
                "teams": ctx.teams,
                "scoring_type": ctx.scoring_type,
            },
            "top_3": [candidate.as_dict() for candidate in candidates[:3]],
            "llm_recommendation": reasoning.parsed,
            "mcp_sources_used": sorted(ctx.mcp_data.keys()),
        }


def format_recommendation(result: dict[str, Any]) -> str:
    lines = []
    draft = result["draft"]
    lines.append(f"Draft {draft.get('draft_id')} | pick {draft['pick_no']} | slot {draft['my_slot']} | {draft['scoring_type']}")
    lines.append(f"Reasoning provider: {result['provider']}")
    if result.get("reasoning_error"):
        lines.append(f"Fallback note: {result['reasoning_error']}")
    lines.append("")
    lines.append("Top 3 local scores:")
    for idx, candidate in enumerate(result["top_3"], start=1):
        lines.append(
            f"{idx}. {candidate['name']} ({candidate['position']}, {candidate.get('team') or 'FA'}) "
            f"score {candidate['score']} | proj {candidate['projected_season_points']} season / "
            f"{candidate['projected_fp_per_game']} fp/g | confidence inputs: {', '.join(candidate['major_factors'][:3])}"
        )
    llm = result.get("llm_recommendation") or {}
    if llm:
        lines.append("")
        lines.append(f"Final recommendation: {llm.get('final_recommendation')}")
        if llm.get("strategy_note"):
            lines.append(f"Strategy: {llm['strategy_note']}")
    if result.get("mcp_sources_used"):
        lines.append("")
        lines.append("NFL MCP sources used: " + ", ".join(result["mcp_sources_used"]))
    return "\n".join(lines)

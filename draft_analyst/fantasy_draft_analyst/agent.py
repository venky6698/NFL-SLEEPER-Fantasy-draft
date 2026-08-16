from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings
from .http_json import HttpError, request_json, url_join
from .live_sync import LiveDraftSnapshot
from .mcp_client import McpClient
from .models import DraftContext
from .reasoning import ReasoningResult, choose_reasoning
from .scoring import score_candidates
from .sleeper import SleeperClient
from .weekly import top_by_position_with_weekly


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

    def build_context(
        self,
        manual_state_path: str | None = None,
        live_snapshot: LiveDraftSnapshot | None = None,
    ) -> DraftContext:
        manual_notes: dict[str, Any] = {}
        if manual_state_path:
            manual_notes = json.loads(Path(manual_state_path).read_text())

        if manual_notes.get("draft_id"):
            draft_id = str(manual_notes["draft_id"])
        elif live_snapshot:
            draft_id = str(live_snapshot.draft_id)
        else:
            draft_id = self.discover_draft_id()
        draft = manual_notes.get("draft") or (live_snapshot.draft if live_snapshot else self.sleeper.draft(draft_id))
        picks = manual_notes.get("picks") or (live_snapshot.picks if live_snapshot else self.sleeper.draft_picks(draft_id))
        players = manual_notes.get("players") or (live_snapshot.players if live_snapshot else self.sleeper.players())
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
            sync_metadata={
                "source": "live_sync" if live_snapshot else "direct_fetch",
                "synced_at": live_snapshot.synced_at if live_snapshot else None,
                "sync_error": live_snapshot.error if live_snapshot else None,
                "drafted_player_ids": sorted(str(pick.get("player_id")) for pick in picks if pick.get("player_id")),
                "last_pick": (live_snapshot.board_rows()[-1] if live_snapshot and live_snapshot.picks else None),
            },
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

    def recommend(
        self,
        manual_state_path: str | None = None,
        live_snapshot: LiveDraftSnapshot | None = None,
    ) -> dict[str, Any]:
        ctx = self.build_context(manual_state_path, live_snapshot)
        candidates = score_candidates(ctx)
        reasoning: ReasoningResult = choose_reasoning(self.settings, ctx, candidates)
        reasoning_payload = enforce_available_recommendation(reasoning.parsed, candidates)
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
                "synced_at": ctx.sync_metadata.get("synced_at"),
                "sync_age_seconds": ctx.seconds_since_sync,
                "drafted_player_count": len(ctx.picked_player_ids),
                "last_pick": ctx.sync_metadata.get("last_pick"),
            },
            "top_3": [candidate.as_dict() for candidate in candidates[:3]],
            "llm_recommendation": reasoning_payload,
            "mcp_sources_used": sorted(ctx.mcp_data.keys()),
        }

    def position_report(
        self,
        *,
        positions: list[str] | None = None,
        limit: int = 30,
        season: int = 2026,
        manual_state_path: str | None = None,
        live_snapshot: LiveDraftSnapshot | None = None,
    ) -> dict[str, Any]:
        ctx = self.build_context(manual_state_path, live_snapshot)
        candidates = score_candidates(ctx, limit_per_position=max(limit, 80))
        report = top_by_position_with_weekly(candidates, self.mcp, positions=positions, limit=limit, season=season)
        report["draft"] = {
            "draft_id": ctx.draft.get("draft_id"),
            "pick_no": ctx.current_pick_no,
            "my_slot": ctx.my_slot,
            "drafted_player_count": len(ctx.picked_player_ids),
            "scoring_type": ctx.scoring_type,
        }
        return report


def enforce_available_recommendation(parsed: Any, candidates: list[Any]) -> Any:
    if not candidates:
        return parsed
    if isinstance(parsed, list):
        parsed = {
            "top_3": [item for item in parsed if isinstance(item, dict)][:3],
            "final_recommendation": parsed[0].get("name") if parsed and isinstance(parsed[0], dict) else None,
            "strategy_note": "LLM returned a list; normalized to the expected recommendation object.",
        }
    if not isinstance(parsed, dict):
        return parsed

    available_by_id = {str(candidate.player_id): candidate for candidate in candidates}
    available_by_name = {candidate.name.casefold(): candidate for candidate in candidates}
    top_candidate = candidates[0]

    final = parsed.get("final_recommendation")
    final_text = str(final or "")
    final_available = False
    for candidate in candidates:
        if str(candidate.player_id) == final_text or candidate.name.casefold() in final_text.casefold():
            final_available = True
            break

    if final_text in available_by_id:
        candidate = available_by_id[final_text]
        parsed = dict(parsed)
        parsed["final_recommendation"] = f"{candidate.name} ({candidate.position}, {candidate.team or 'FA'})"
    elif not final:
        parsed = dict(parsed)
        parsed["availability_override"] = "LLM omitted final_recommendation. Using top live candidate instead."
        parsed["final_recommendation"] = f"{top_candidate.name} ({top_candidate.position}, {top_candidate.team or 'FA'})"
    elif not final_available:
        parsed = dict(parsed)
        parsed["availability_override"] = (
            f"LLM final recommendation '{final}' was not in the live available-player set. "
            f"Using top live candidate instead."
        )
        parsed["final_recommendation"] = f"{top_candidate.name} ({top_candidate.position}, {top_candidate.team or 'FA'})"

    clean_top_3 = []
    for item in parsed.get("top_3") or []:
        if not isinstance(item, dict):
            continue
        player_id = str(item.get("player_id") or "")
        name = str(item.get("name") or "").casefold()
        if player_id in available_by_id or name in available_by_name:
            clean_top_3.append(item)

    if len(clean_top_3) < 3:
        existing_ids = {str(item.get("player_id")) for item in clean_top_3 if isinstance(item, dict)}
        for candidate in candidates:
            if candidate.player_id in existing_ids:
                continue
            clean_top_3.append(
                {
                    "player_id": candidate.player_id,
                    "name": candidate.name,
                    "confidence": 0.75,
                    "why": candidate.major_factors[:4],
                    "risk": [factor for factor in candidate.major_factors if "risk" in factor or "flag" in factor]
                    or ["no major availability risk in local data"],
                }
            )
            if len(clean_top_3) == 3:
                break

    if clean_top_3:
        parsed = dict(parsed)
        parsed["top_3"] = clean_top_3
    return parsed


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
        if llm.get("availability_override"):
            lines.append(f"Availability guard: {llm['availability_override']}")
        if llm.get("strategy_note"):
            lines.append(f"Strategy: {llm['strategy_note']}")
    if result.get("mcp_sources_used"):
        lines.append("")
        lines.append("NFL MCP sources used: " + ", ".join(result["mcp_sources_used"]))
    return "\n".join(lines)

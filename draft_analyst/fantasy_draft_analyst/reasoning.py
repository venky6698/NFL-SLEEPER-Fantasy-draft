from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .http_json import HttpError, request_json, url_join
from .models import Candidate, DraftContext


SYSTEM_PROMPT = """You are an elite fantasy football draft analyst.
Use the supplied live draft state and candidate metrics. Return compact JSON only.
Do not invent injuries, coaching facts, odds, or schedule edges that are not in the input.
Prefer explainable, risk-aware recommendations over name value.
"""


def build_reasoning_payload(ctx: DraftContext, candidates: list[Candidate]) -> dict[str, Any]:
    return {
        "draft": {
            "draft_id": ctx.draft.get("draft_id"),
            "type": ctx.draft.get("type"),
            "status": ctx.draft.get("status"),
            "teams": ctx.teams,
            "rounds": ctx.rounds,
            "current_pick_no": ctx.current_pick_no,
            "my_slot": ctx.my_slot,
            "scoring_type": ctx.scoring_type,
            "settings": ctx.draft.get("settings", {}),
        },
        "recent_picks": ctx.picks[-24:],
        "my_roster_counts": dict(__import__("collections").Counter(
            (pick.get("metadata") or {}).get("position")
            for pick in ctx.picks
            if int(pick.get("draft_slot") or 0) == ctx.my_slot and (pick.get("metadata") or {}).get("position")
        )),
        "mcp_data": ctx.mcp_data,
        "manual_notes": ctx.manual_notes,
        "candidates": [c.as_dict() for c in candidates[:12]],
        "required_output_schema": {
            "top_3": [
                {
                    "player_id": "string",
                    "name": "string",
                    "confidence": "0-1 number",
                    "why": ["short factor"],
                    "risk": ["short risk"],
                }
            ],
            "final_recommendation": "string",
            "strategy_note": "string",
        },
    }


@dataclass
class ReasoningResult:
    provider: str
    text: str
    parsed: dict[str, Any] | None = None
    error: str | None = None


class Reasoner:
    def analyze(self, ctx: DraftContext, candidates: list[Candidate]) -> ReasoningResult:
        raise NotImplementedError


@dataclass
class AbacusReasoner(Reasoner):
    settings: Settings

    def analyze(self, ctx: DraftContext, candidates: list[Candidate]) -> ReasoningResult:
        if not self.settings.abacus_api_key:
            return ReasoningResult("abacus", "", error="ABACUS_API_KEY is not set")
        payload = build_reasoning_payload(ctx, candidates)
        body = {
            "model": self.settings.abacus_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, separators=(",", ":"))},
            ],
            "temperature": 0.2,
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
        }
        try:
            response = request_json(
                "POST",
                url_join(self.settings.abacus_base_url, "/chat/completions"),
                headers={"Authorization": f"Bearer {self.settings.abacus_api_key}"},
                body=body,
                timeout=60,
            )
            text = response["choices"][0]["message"]["content"]
            return ReasoningResult("abacus", text, parsed=json.loads(text))
        except Exception as exc:
            return ReasoningResult("abacus", "", error=str(exc))


@dataclass
class OllamaReasoner(Reasoner):
    settings: Settings

    def analyze(self, ctx: DraftContext, candidates: list[Candidate]) -> ReasoningResult:
        payload = build_reasoning_payload(ctx, candidates)
        prompt = SYSTEM_PROMPT + "\n\nReturn JSON for this draft state:\n" + json.dumps(payload, separators=(",", ":"))
        body = {
            "model": self.settings.ollama_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }
        try:
            response = request_json("POST", url_join(self.settings.ollama_url, "/api/chat"), body=body, timeout=90)
            text = response.get("message", {}).get("content", "")
            return ReasoningResult("ollama", text, parsed=json.loads(text) if text else None)
        except Exception as exc:
            if isinstance(exc, HttpError):
                return ReasoningResult("ollama", "", error=str(exc))
            return ReasoningResult("ollama", "", error=str(exc))


def local_result(candidates: list[Candidate]) -> ReasoningResult:
    top = candidates[:3]
    parsed = {
        "top_3": [
            {
                "player_id": c.player_id,
                "name": c.name,
                "confidence": round(max(0.45, min(0.92, c.score / max(1.0, top[0].score))), 2),
                "why": c.major_factors[:4],
                "risk": [f for f in c.major_factors if "risk" in f or "flag" in f] or ["no major availability risk in local data"],
            }
            for c in top
        ],
        "final_recommendation": top[0].name if top else "No candidate found",
        "strategy_note": "Local deterministic model used; Abacus/Ollama refinement was unavailable.",
    }
    return ReasoningResult("local", json.dumps(parsed), parsed=parsed)


def choose_reasoning(settings: Settings, ctx: DraftContext, candidates: list[Candidate]) -> ReasoningResult:
    abacus = AbacusReasoner(settings).analyze(ctx, candidates)
    if abacus.parsed:
        return abacus
    ollama = OllamaReasoner(settings).analyze(ctx, candidates)
    if ollama.parsed:
        return ollama
    result = local_result(candidates)
    errors = [f"Abacus: {abacus.error}", f"Ollama: {ollama.error}"]
    result.error = "; ".join(error for error in errors if error)
    return result

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from typing import Any

from .models import Candidate, DraftContext, FANTASY_POSITIONS


BASELINES = {
    "QB": {"points": 295, "games": 17, "replacement_rank": 12},
    "RB": {"points": 185, "games": 16, "replacement_rank": 30},
    "WR": {"points": 190, "games": 16, "replacement_rank": 36},
    "TE": {"points": 125, "games": 16, "replacement_rank": 12},
    "K": {"points": 125, "games": 17, "replacement_rank": 12},
    "DEF": {"points": 115, "games": 17, "replacement_rank": 12},
}

POSITION_MULTIPLIER_BY_SCORING = {
    "ppr": {"RB": 1.02, "WR": 1.08, "TE": 1.08, "QB": 1.0, "K": 1.0, "DEF": 1.0},
    "half_ppr": {"RB": 1.04, "WR": 1.04, "TE": 1.04, "QB": 1.0, "K": 1.0, "DEF": 1.0},
    "standard": {"RB": 1.08, "WR": 0.98, "TE": 0.98, "QB": 1.0, "K": 1.0, "DEF": 1.0},
}


def pick_number_for_slot(next_pick: int, teams: int, slot: int) -> int:
    round_no = math.ceil(next_pick / teams)
    if round_no % 2 == 1:
        target = (round_no - 1) * teams + slot
    else:
        target = round_no * teams - slot + 1
    if target < next_pick:
        return pick_number_for_slot((round_no * teams) + 1, teams, slot)
    return target


def estimate_next_pick_after_current(current_pick: int, teams: int, slot: int) -> int:
    first = pick_number_for_slot(current_pick, teams, slot)
    return pick_number_for_slot(first + 1, teams, slot)


def my_roster_counts(ctx: DraftContext) -> Counter:
    counts: Counter = Counter()
    for pick in ctx.picks:
        if int(pick.get("draft_slot") or 0) == ctx.my_slot:
            meta = pick.get("metadata") or {}
            pos = meta.get("position")
            if not pos and pick.get("player_id"):
                pos = (ctx.players.get(str(pick["player_id"])) or {}).get("position")
            if pos:
                counts[str(pos).upper()] += 1
    return counts


def roster_need_score(ctx: DraftContext, position: str) -> float:
    settings = ctx.draft.get("settings", {})
    slots = {
        "QB": int(settings.get("slots_qb", 1) or 0),
        "RB": int(settings.get("slots_rb", 2) or 0),
        "WR": int(settings.get("slots_wr", 2) or 0),
        "TE": int(settings.get("slots_te", 1) or 0),
        "K": int(settings.get("slots_k", 1) or 0),
        "DEF": int(settings.get("slots_def", 1) or 0),
    }
    flex = int(settings.get("slots_flex", 0) or settings.get("slots_wrrbte_flex", 0) or 0)
    super_flex = int(settings.get("slots_super_flex", 0) or settings.get("slots_qb_flex", 0) or 0)
    counts = my_roster_counts(ctx)
    required = slots.get(position, 0)
    if position in {"RB", "WR", "TE"}:
        required += flex / 3
    if position == "QB":
        required += super_flex
    have = counts[position]
    if have < required:
        return 1.0
    if position in {"RB", "WR"} and have < required + 2:
        return 0.75
    if position in {"QB", "TE"} and have < required + 1:
        return 0.58
    if position in {"K", "DEF"} and ctx.current_pick_no < ctx.teams * (ctx.rounds - 2):
        return 0.25
    return 0.45


def normalize_adp(player: dict[str, Any], fallback: float) -> float:
    candidates = [
        player.get("fantasy_data_id"),
        player.get("search_rank"),
        (player.get("metadata") or {}).get("adp"),
        player.get("adp"),
    ]
    for value in candidates:
        try:
            number = float(value)
            if 0 < number < 500:
                return number
        except (TypeError, ValueError):
            continue
    return fallback


def estimate_points(position: str, adp: float, scoring_type: str) -> tuple[float, float, float]:
    baseline = BASELINES[position]
    scarcity_curve = {"QB": 0.45, "RB": 0.9, "WR": 0.78, "TE": 0.72, "K": 0.2, "DEF": 0.25}[position]
    starter_pick_value = max(0.0, 260.0 - adp) * scarcity_curve
    points = baseline["points"] + starter_pick_value
    scoring_key = "half_ppr" if "half" in scoring_type else "standard" if "standard" in scoring_type else "ppr"
    points *= POSITION_MULTIPLIER_BY_SCORING[scoring_key].get(position, 1.0)
    games = baseline["games"]
    floor = points * (0.72 if position in {"RB", "WR", "TE"} else 0.78)
    ceiling = points * (1.24 if position in {"RB", "WR", "TE"} else 1.14)
    return points, points / games, ceiling - floor


def injury_risk(player: dict[str, Any]) -> tuple[float, list[str]]:
    factors: list[str] = []
    status = str(player.get("injury_status") or player.get("status") or "").lower()
    if status in {"out", "ir", "pup", "suspended"}:
        factors.append(f"availability flag: {status}")
        return 0.85, factors
    if status in {"questionable", "doubtful"}:
        factors.append(f"injury flag: {status}")
        return 0.45, factors
    age = player.get("age")
    try:
        age_float = float(age)
        if age_float >= 30 and player.get("position") in {"RB", "WR"}:
            factors.append("age curve risk")
            return 0.25, factors
    except (TypeError, ValueError):
        pass
    return 0.08, factors


def build_positional_available(ctx: DraftContext) -> dict[str, list[tuple[str, dict[str, Any], float]]]:
    available: dict[str, list[tuple[str, dict[str, Any], float]]] = defaultdict(list)
    fallback_rank = 350.0
    for player_id, player in ctx.players.items():
        pos = str(player.get("position") or "").upper()
        if player_id in ctx.picked_player_ids or pos not in FANTASY_POSITIONS:
            continue
        if player.get("active") is False and pos != "DEF":
            continue
        if pos in {"QB", "RB", "WR", "TE", "K"} and not (player.get("team") or player.get("team_abbr")):
            continue
        name = player.get("full_name") or player.get("first_name") or player.get("last_name")
        if not name and pos != "DEF":
            continue
        adp = normalize_adp(player, fallback_rank)
        available[pos].append((player_id, player, adp))
    for pos in available:
        available[pos].sort(key=lambda item: item[2])
    return available


def positional_run_pressure(ctx: DraftContext, position: str) -> float:
    recent = ctx.picks[-max(1, ctx.teams) :]
    if not recent:
        return 0.0
    counts = Counter()
    for pick in recent:
        meta = pick.get("metadata") or {}
        pos = str(meta.get("position") or "").upper()
        if pos:
            counts[pos] += 1
    return min(1.0, counts[position] / max(3, len(recent) / 2))


def survival_probability(adp: float, next_pick_after_current: int, current_pick: int) -> float:
    # Logistic approximation: players with ADP well before the next turn rarely survive.
    if adp <= current_pick:
        return 0.05
    spread = 10.0
    return 1.0 / (1.0 + math.exp(-(adp - next_pick_after_current) / spread))


def score_candidates(ctx: DraftContext, limit_per_position: int = 18) -> list[Candidate]:
    available = build_positional_available(ctx)
    next_pick = estimate_next_pick_after_current(ctx.current_pick_no, ctx.teams, ctx.my_slot)
    candidates: list[Candidate] = []
    for position, rows in available.items():
        replacement_index = min(len(rows) - 1, BASELINES[position]["replacement_rank"])
        replacement_adp = rows[replacement_index][2] if rows else 300.0
        replacement_points, _, _ = estimate_points(position, replacement_adp, ctx.scoring_type)
        adps = [row[2] for row in rows[: max(limit_per_position, 30)]]
        tier_gap_cutoff = statistics.mean(adps) + statistics.pstdev(adps) if len(adps) > 2 else 999.0
        for player_id, player, adp in rows[:limit_per_position]:
            points, fpg, volatility = estimate_points(position, adp, ctx.scoring_type)
            vbd = max(0.0, points - replacement_points)
            risk, risk_factors = injury_risk(player)
            run = positional_run_pressure(ctx, position)
            top_remaining_same_pos = rows[:8]
            scarcity = 1.0 - min(1.0, len(top_remaining_same_pos) / 10.0)
            if adp < tier_gap_cutoff:
                scarcity += 0.15
            scarcity = min(1.0, scarcity + run * 0.25)
            roster_fit = roster_need_score(ctx, position)
            survive = survival_probability(adp, next_pick, ctx.current_pick_no)
            opportunity = 0.7 if position in {"RB", "WR", "TE"} else 0.55
            if player.get("depth_chart_order") in {1, "1"}:
                opportunity += 0.15
            team_context = 0.6
            if player.get("team"):
                team_context += 0.05
            schedule_context = 0.55
            raw_score = (
                vbd * 0.38
                + points * 0.12
                + scarcity * 35
                + roster_fit * 28
                + (1 - survive) * 18
                + opportunity * 12
                + team_context * 8
                + schedule_context * 6
                - risk * 35
                - volatility * 0.03
            )
            factors = [
                f"{position} value over replacement {vbd:.1f}",
                f"{survive:.0%} chance to survive to your next pick",
                f"roster fit {roster_fit:.0%}",
            ]
            if scarcity > 0.4:
                factors.append("scarcity/tier pressure at position")
            if run > 0.3:
                factors.append("recent positional run detected")
            factors.extend(risk_factors)
            candidates.append(
                Candidate(
                    player_id=player_id,
                    name=player.get("full_name") or player.get("search_full_name") or player.get("last_name") or player_id,
                    position=position,
                    team=player.get("team"),
                    age=float(player["age"]) if str(player.get("age", "")).replace(".", "", 1).isdigit() else None,
                    adp=adp,
                    projected_season_points=points,
                    projected_fp_per_game=fpg,
                    floor=max(0.0, points - volatility / 2),
                    ceiling=points + volatility / 2,
                    vbd=vbd,
                    scarcity=scarcity,
                    roster_fit=roster_fit,
                    survival_probability=survive,
                    risk=risk,
                    opportunity=min(1.0, opportunity),
                    team_context=min(1.0, team_context),
                    schedule_context=schedule_context,
                    score=raw_score,
                    major_factors=factors,
                    source_quality=["Sleeper live draft", "Sleeper player pool", "local VBD/scarcity model"],
                )
            )
    return sorted(candidates, key=lambda c: c.score, reverse=True)

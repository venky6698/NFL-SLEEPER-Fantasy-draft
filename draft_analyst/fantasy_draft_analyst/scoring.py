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

DRAFT_SCORE_WEIGHTS = {
    "role": 0.35,
    "talent": 0.25,
    "team_environment": 0.20,
    "ceiling": 0.10,
    "schedule": 0.05,
    "risk": -0.05,
}

POSITION_ABSOLUTE_FPG_CAPS = {
    "QB": 25.2,
    "RB": 23.0,
    "WR": 23.5,
    "TE": 18.5,
    "K": 10.0,
    "DEF": 10.0,
}

TEAM_ENVIRONMENT_PRIORS = {
    "BUF": 88,
    "BAL": 86,
    "PHI": 86,
    "DET": 85,
    "CIN": 84,
    "KC": 84,
    "DAL": 82,
    "HOU": 81,
    "LAR": 81,
    "MIA": 81,
    "SF": 81,
    "ATL": 79,
    "GB": 79,
    "LAC": 79,
    "WAS": 79,
    "CHI": 77,
    "DEN": 77,
    "IND": 77,
    "JAX": 76,
    "MIN": 76,
    "SEA": 75,
    "TB": 75,
    "ARI": 73,
    "LV": 72,
    "NE": 72,
    "NO": 71,
    "PIT": 71,
    "TEN": 70,
    "CAR": 69,
    "CLE": 69,
    "NYG": 68,
    "NYJ": 68,
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


def current_round(ctx: DraftContext) -> int:
    return max(1, math.ceil(ctx.current_pick_no / max(1, ctx.teams)))


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


def is_one_qb_ppr_redraft(ctx: DraftContext) -> bool:
    settings = ctx.draft.get("settings", {})
    qb_slots = int(settings.get("slots_qb", 1) or 0)
    super_flex = int(settings.get("slots_super_flex", 0) or settings.get("slots_qb_flex", 0) or 0)
    return qb_slots <= 1 and super_flex == 0 and "ppr" in ctx.scoring_type


def roster_strategy_summary(ctx: DraftContext) -> dict[str, Any]:
    settings = ctx.draft.get("settings", {})
    counts = my_roster_counts(ctx)
    rb_required = int(settings.get("slots_rb", 2) or 0)
    wr_required = int(settings.get("slots_wr", 2) or 0)
    te_required = int(settings.get("slots_te", 1) or 0)
    qb_required = int(settings.get("slots_qb", 1) or 0)
    flex = int(settings.get("slots_flex", 0) or settings.get("slots_wrrbte_flex", 0) or 0)
    rb_wr_core = counts["RB"] + counts["WR"]
    strategy_format = (
        f"{ctx.teams}-team 1-QB PPR redraft strategy"
        if is_one_qb_ppr_redraft(ctx)
        else "league settings strategy"
    )
    return {
        "format": strategy_format,
        "round": current_round(ctx),
        "rb_required": rb_required,
        "wr_required": wr_required,
        "te_required": te_required,
        "qb_required": qb_required,
        "flex": flex,
        "current_roster_counts": dict(counts),
        "rb_wr_core_count": rb_wr_core,
        "rules": [
            "Use ADP as market price, not as the ranking.",
            "Recommend from projected points above replacement, tier drop, survival risk, roster fit, and ADP value.",
            "In 1-QB PPR, wait on QB unless an elite tier falls below market price.",
            "Prefer RB/WR anchors early; RB gets the coin-flip edge only when the value gap is real.",
            "Draft into a positional run only when the current tier is about to disappear.",
            "Use late rounds for contingent-upside RBs, target-earning WRs, and D/ST or kicker last.",
        ],
    }


def draft_strategy_modifiers(
    ctx: DraftContext,
    position: str,
    adp: float,
    vbd: float,
    scarcity: float,
    survival: float,
    roster_fit: float,
) -> tuple[dict[str, float], list[str]]:
    round_no = current_round(ctx)
    counts = my_roster_counts(ctx)
    settings = ctx.draft.get("settings", {})
    rb_slots = int(settings.get("slots_rb", 2) or 0)
    wr_slots = int(settings.get("slots_wr", 2) or 0)
    flex = int(settings.get("slots_flex", 0) or settings.get("slots_wrrbte_flex", 0) or 0)
    one_qb_ppr = is_one_qb_ppr_redraft(ctx)
    adp_delta = ctx.current_pick_no - adp
    is_reach = adp_delta < -ctx.teams
    is_value = adp_delta > ctx.teams / 2
    tier_breaker = scarcity >= 0.45 or survival <= 0.18

    modifiers: dict[str, float] = {
        "strategy_adp_value": clamp(adp_delta / max(1, ctx.teams), -1.25, 1.5) * 4,
        "strategy_tier_drop": (scarcity * 0.25 + (1 - survival) * 0.15) * 20,
    }
    factors: list[str] = [
        f"strategy formula: VOR + tier urgency + survival risk + roster fit + ADP value",
    ]
    if is_value:
        factors.append("market value: available later than ADP")
    if is_reach:
        factors.append("ADP reach guardrail applied")
    if tier_breaker:
        factors.append("tier-breaker/survival trigger")

    if one_qb_ppr:
        rb_wr_core = counts["RB"] + counts["WR"]
        rb_need = max(0, rb_slots - counts["RB"])
        wr_need = max(0, wr_slots - counts["WR"])
        starting_core_need = rb_need + wr_need + max(0, flex - max(0, rb_wr_core - rb_slots - wr_slots))

        if position in {"RB", "WR"}:
            if round_no <= 3 and rb_wr_core < 2:
                modifiers["strategy_anchor_core"] = 7.0
                factors.append("strategy: build two RB/WR anchors by Round 3")
            elif round_no <= 6 and starting_core_need > 0:
                modifiers["strategy_starting_core"] = 5.5
                factors.append("strategy: complete RB/WR starting core before bench picks")
            if position == "RB" and round_no <= 4 and counts["RB"] < 1 and vbd >= 20:
                modifiers["strategy_rb_scarcity_coinflip"] = 4.5
                factors.append("strategy: RB gets coin-flip edge only with a real VOR gap")
            if position == "WR" and "ppr" in ctx.scoring_type and round_no >= 3:
                modifiers["strategy_ppr_wr_depth"] = 2.0
                factors.append("strategy: PPR target volume supports WR/flex depth")
            if round_no >= 9 and position == "RB" and roster_fit >= 0.5:
                modifiers["strategy_late_rb_upside"] = 4.0
                factors.append("strategy: late RB contingent-upside portfolio")

        if position == "QB":
            elite_qb_value = adp <= 36 and is_value
            if round_no <= 5 and not elite_qb_value:
                modifiers["strategy_wait_on_qb"] = -9.0
                factors.append("strategy: 1-QB PPR waits on QB unless elite value falls")
            elif counts["QB"] == 0 and 7 <= round_no <= 10:
                modifiers["strategy_qb_value_window"] = 4.5
                factors.append("strategy: discounted starting-QB window")
            if counts["QB"] >= 1:
                modifiers["strategy_no_early_backup_qb"] = -12.0
                factors.append("strategy: avoid backup QB before core depth is built")

        if position == "TE":
            elite_te_value = adp <= 36 and (is_value or tier_breaker)
            if round_no <= 6 and elite_te_value and counts["TE"] == 0:
                modifiers["strategy_elite_te_value"] = 4.0
                factors.append("strategy: elite TE only when value/tier edge is real")
            elif round_no <= 8 and counts["TE"] == 0 and not elite_te_value:
                modifiers["strategy_te_patience"] = -2.5
                factors.append("strategy: wait for next usable TE tier")
            if counts["TE"] >= 1 and round_no < 12:
                modifiers["strategy_no_early_backup_te"] = -8.0
                factors.append("strategy: avoid early backup TE in single-TE format")

        if position in {"K", "DEF"}:
            final_round_window = max(1, ctx.rounds - 1)
            if round_no < final_round_window:
                modifiers["strategy_stream_k_def_late"] = -24.0
                factors.append("strategy: stream D/ST and kicker; draft them last")

    return modifiers, factors


def normalize_adp(player: dict[str, Any], fallback: float) -> float:
    candidates = [
        (player.get("metadata") or {}).get("adp"),
        player.get("adp"),
        player.get("search_rank"),
    ]
    for value in candidates:
        try:
            number = float(value)
            if 0 < number < 500:
                return number
        except (TypeError, ValueError):
            continue
    return fallback


def market_ppg_prior(position: str, adp: float, scoring_type: str) -> float:
    rank = max(1.0, min(350.0, adp))
    if position == "QB":
        ppg = 25.0 - 0.58 * math.log(rank)
    elif position == "RB":
        ppg = 22.8 - 0.24 * (rank - 1) ** 0.78
    elif position == "WR":
        ppg = 23.0 - 0.21 * (rank - 1) ** 0.80
    elif position == "TE":
        ppg = 18.2 - 0.20 * (rank - 1) ** 0.82
    elif position == "K":
        ppg = 9.6 - 0.012 * rank
    else:
        ppg = 9.4 - 0.010 * rank

    scoring_key = "half_ppr" if "half" in scoring_type else "standard" if "standard" in scoring_type else "ppr"
    if scoring_key == "half_ppr" and position in {"RB", "WR", "TE"}:
        ppg *= 0.93
    elif scoring_key == "standard" and position in {"WR", "TE"}:
        ppg *= 0.82
    elif scoring_key == "standard" and position == "RB":
        ppg *= 0.90
    floor_by_position = {"QB": 12.0, "RB": 5.0, "WR": 5.0, "TE": 3.5, "K": 5.0, "DEF": 4.5}
    return clamp(ppg, floor_by_position[position], POSITION_ABSOLUTE_FPG_CAPS[position])


def estimate_points(position: str, adp: float, scoring_type: str) -> tuple[float, float, float]:
    fpg = market_ppg_prior(position, adp, scoring_type)
    games = BASELINES[position]["games"]
    points = fpg * games
    volatility_rate = {"QB": 0.26, "RB": 0.48, "WR": 0.50, "TE": 0.46, "K": 0.24, "DEF": 0.30}[position]
    return points, fpg, points * volatility_rate


def parse_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def role_history_cap(position: str, player: dict[str, Any]) -> tuple[float | None, list[str]]:
    factors: list[str] = []
    years_exp = parse_float(player.get("years_exp"))
    depth_order = parse_float(player.get("depth_chart_order"))
    if years_exp is None:
        metadata = player.get("metadata") or {}
        rookie_year = parse_float(metadata.get("rookie_year"))
        if rookie_year and rookie_year >= 2024:
            years_exp = 1

    if position == "RB":
        if depth_order and depth_order >= 3:
            factors.append("RB depth-chart role cap")
            return 8.0, factors
        if depth_order == 2:
            factors.append("RB2 committee role cap")
            if years_exp is not None and years_exp <= 1:
                factors.append("limited last-two-year NFL production; committee RB cap")
                return 10.8, factors
            return 12.5, factors
        if years_exp is not None and years_exp <= 1 and (not depth_order or depth_order >= 2):
            factors.append("limited last-two-year NFL production; committee RB cap")
            return 10.8, factors
        if years_exp is not None and years_exp <= 2 and depth_order and depth_order >= 2:
            factors.append("limited last-two-year RB production")
            return 11.5, factors
    if position == "WR":
        if years_exp is not None and years_exp <= 1 and depth_order and depth_order >= 3:
            factors.append("limited last-two-year WR production")
            return 8.5, factors
    if position == "TE":
        if years_exp is not None and years_exp <= 1 and depth_order and depth_order >= 2:
            factors.append("limited last-two-year TE production")
            return 7.5, factors
    return None, factors


def estimate_player_points(
    player: dict[str, Any],
    position: str,
    adp: float,
    scoring_type: str,
) -> tuple[float, float, float, list[str]]:
    points, fpg, volatility = estimate_points(position, adp, scoring_type)
    max_fpg = POSITION_ABSOLUTE_FPG_CAPS[position]
    if fpg > max_fpg:
        games = BASELINES[position]["games"]
        points = max_fpg * games
        fpg = max_fpg
        volatility = min(volatility, points * 0.48)
    cap, factors = role_history_cap(position, player)
    if cap is not None and fpg > cap:
        games = BASELINES[position]["games"]
        points = cap * games
        fpg = cap
        volatility = min(volatility, points * 0.45)
    return points, fpg, volatility, factors


def component_scores(
    player: dict[str, Any],
    position: str,
    adp: float,
    points: float,
    fpg: float,
    floor: float,
    ceiling: float,
    risk: float,
    opportunity: float,
    team_context: float,
    schedule_context: float,
    scarcity: float,
) -> dict[str, float]:
    depth_order = parse_float(player.get("depth_chart_order"))
    years_exp = parse_float(player.get("years_exp"))
    market_rank = adp
    team = str(player.get("team") or player.get("team_abbr") or "").upper()

    role = 50 + opportunity * 16
    role += max(0.0, 15 - 3.0 * math.log(max(1.0, market_rank)))
    if position == "QB" and market_rank <= 75:
        role += 4
    if position == "QB" and market_rank <= 24:
        role += 5
    if position in {"RB", "WR", "TE"} and market_rank <= 36:
        role += 3
    if depth_order == 1:
        role += 7
    elif depth_order == 2:
        role -= 12
    elif depth_order and depth_order >= 3:
        role -= 26
    if position in {"RB", "WR", "TE"} and fpg >= 15:
        role += min(4, (fpg - 15) * 0.8)

    talent = 96 - min(58, 8.8 * math.log(max(1.0, market_rank)))
    if years_exp is not None and years_exp <= 1:
        talent -= 7
    elif years_exp is not None and 2 <= years_exp <= 5:
        talent += 3
    elif years_exp is not None and years_exp >= 9 and position in {"RB", "WR"}:
        talent -= 6
    if fpg >= 18:
        talent += min(5, (fpg - 18) * 1.2)
    elif fpg < 9 and position in {"RB", "WR", "TE"}:
        talent -= 6

    team_environment = TEAM_ENVIRONMENT_PRIORS.get(team, 72 if team else 55)
    team_environment = team_environment * 0.8 + team_context * 20
    if depth_order and depth_order > 1:
        team_environment -= 5

    max_fpg = POSITION_ABSOLUTE_FPG_CAPS[position]
    ceiling_score = 45 + (fpg / max_fpg) * 24
    ceiling_score += max(0.0, 10 - 1.8 * math.log(max(1.0, market_rank)))
    ceiling_score += min(8, max(0, ceiling - floor) / max(1, points) * 12)
    if market_rank <= 12:
        ceiling_score += 6
    elif market_rank <= 36:
        ceiling_score += 3
    if scarcity > 0.45:
        ceiling_score += 3

    return {
        "role": clamp(role),
        "talent": clamp(talent),
        "team_environment": clamp(team_environment),
        "ceiling": clamp(ceiling_score),
        "schedule": clamp(schedule_context * 100),
        "risk": clamp(risk * 100),
    }


def weighted_preseason_score(components: dict[str, float]) -> float:
    return sum(components[key] * weight for key, weight in DRAFT_SCORE_WEIGHTS.items())


def live_draft_modifiers(
    vbd: float,
    roster_fit: float,
    scarcity: float,
    survival: float,
    run: float,
) -> dict[str, float]:
    return {
        "value_over_replacement": min(12.0, max(0.0, vbd) * 0.05),
        "roster_fit": (roster_fit - 0.5) * 10,
        "scarcity": scarcity * 8,
        "survival_urgency": (1 - survival) * 7,
        "positional_run": run * 4,
    }


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
        replacement_player = rows[replacement_index][1] if rows else {}
        replacement_points, _, _, _ = estimate_player_points(
            replacement_player,
            position,
            replacement_adp,
            ctx.scoring_type,
        )
        adps = [row[2] for row in rows[: max(limit_per_position, 30)]]
        tier_gap_cutoff = statistics.mean(adps) + statistics.pstdev(adps) if len(adps) > 2 else 999.0
        for player_id, player, adp in rows[:limit_per_position]:
            points, fpg, volatility, role_history_factors = estimate_player_points(player, position, adp, ctx.scoring_type)
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
            components = component_scores(
                player,
                position,
                adp,
                points,
                fpg,
                max(0.0, points - volatility / 2),
                points + volatility / 2,
                risk,
                min(1.0, opportunity),
                min(1.0, team_context),
                schedule_context,
                scarcity,
            )
            modifiers = live_draft_modifiers(vbd, roster_fit, scarcity, survive, run)
            strategy_modifiers, strategy_factors = draft_strategy_modifiers(
                ctx,
                position,
                adp,
                vbd,
                scarcity,
                survive,
                roster_fit,
            )
            modifiers.update(strategy_modifiers)
            raw_score = weighted_preseason_score(components) + sum(modifiers.values())
            factors = [
                f"draft score gate: role {components['role']:.0f}, talent {components['talent']:.0f}, team {components['team_environment']:.0f}, ceiling {components['ceiling']:.0f}, schedule {components['schedule']:.0f}, risk {components['risk']:.0f}",
                f"{position} value over replacement {vbd:.1f}",
                f"{survive:.0%} chance to survive to your next pick",
                f"roster fit {roster_fit:.0%}",
            ]
            if scarcity > 0.4:
                factors.append("scarcity/tier pressure at position")
            if run > 0.3:
                factors.append("recent positional run detected")
            factors.extend(strategy_factors)
            factors.extend(role_history_factors)
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
                    draft_score_components={**components, **modifiers},
                )
            )
    return sorted(candidates, key=lambda c: c.score, reverse=True)

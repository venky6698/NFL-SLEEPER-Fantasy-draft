from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .mcp_client import McpClient
from .models import Candidate


PRIMARY_WEEKLY_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")


def parse_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def defense_rank_map(mcp: McpClient, positions: list[str], season: int = 2026) -> dict[str, dict[str, dict[str, Any]]]:
    try:
        payload = parse_jsonish(mcp.call_tool("get_defense_rankings", {"positions": positions, "season": season}))
    except Exception:
        return {}
    rankings = payload.get("rankings", {}) if isinstance(payload, dict) else {}
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for position, rows in rankings.items():
        result[position] = {}
        for row in rows or []:
            if isinstance(row, dict) and row.get("team"):
                result[position][str(row["team"]).upper()] = row
    return result


def team_schedule(mcp: McpClient, team: str | None, season: int = 2026) -> list[dict[str, Any]]:
    if not team:
        return []
    try:
        payload = parse_jsonish(mcp.call_tool("get_team_schedule", {"team_id": team, "season": season}))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    schedule = payload.get("schedule") or []
    return [game for game in schedule if isinstance(game, dict)]


def matchup_factor(position: str, opponent: str | None, defense_rankings: dict[str, dict[str, dict[str, Any]]]) -> tuple[float, str]:
    if not opponent:
        return 1.0, "neutral schedule"
    row = defense_rankings.get(position, {}).get(opponent.upper())
    if not row or row.get("is_fallback"):
        return 1.0, "neutral schedule"
    tier = str(row.get("matchup_tier") or "").lower()
    rank = row.get("rank")
    if "easy" in tier or "favorable" in tier:
        return 1.06, f"favorable matchup vs {opponent}"
    if "hard" in tier or "tough" in tier or "difficult" in tier:
        return 0.94, f"tough matchup vs {opponent}"
    try:
        rank_int = int(rank)
        if rank_int <= 10:
            return 0.96, f"above-average defense vs {opponent}"
        if rank_int >= 23:
            return 1.04, f"below-average defense vs {opponent}"
    except (TypeError, ValueError):
        pass
    return 1.0, "neutral schedule"


def weekly_projection(candidate: Candidate, schedule: list[dict[str, Any]], defense_rankings: dict[str, dict[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    if not schedule:
        schedule = [
            {
                "week": week,
                "date": None,
                "opponent": {"abbreviation": "TBD", "name": "TBD"},
                "is_home": None,
                "fantasy_implications": [],
            }
            for week in range(1, 18)
        ]

    base = candidate.projected_fp_per_game
    raw_rows: list[dict[str, Any]] = []
    raw_total = 0.0
    for game in schedule:
        opponent = (game.get("opponent") or {}).get("abbreviation")
        home = game.get("is_home")
        home_factor = 1.03 if home is True else 0.98 if home is False else 1.0
        matchup, matchup_note = matchup_factor(candidate.position, opponent, defense_rankings)
        risk_factor = max(0.82, 1.0 - candidate.risk * 0.12)
        role_factor = 0.96 + candidate.opportunity * 0.08
        projected = base * home_factor * matchup * risk_factor * role_factor
        raw_total += projected
        raw_rows.append(
            {
                "week": game.get("week"),
                "date": game.get("date"),
                "opponent": opponent or "TBD",
                "home_away": "home" if home is True else "away" if home is False else "TBD",
                "raw_projection": projected,
                "matchup_note": matchup_note,
                "context": game.get("fantasy_implications") or [],
            }
        )

    scale = candidate.projected_season_points / raw_total if raw_total > 0 else 1.0
    rows = []
    running = 0.0
    for row in raw_rows:
        points = row.pop("raw_projection") * scale
        running += points
        rows.append({**row, "projected_ppr": round(points, 2)})
    return rows


def top_by_position_with_weekly(
    candidates: list[Candidate],
    mcp: McpClient,
    *,
    positions: list[str] | None = None,
    limit: int = 30,
    season: int = 2026,
) -> dict[str, Any]:
    positions = [pos.upper() for pos in (positions or list(PRIMARY_WEEKLY_POSITIONS))]
    by_position: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.position in positions:
            by_position[candidate.position].append(candidate)

    defense_rankings = defense_rank_map(mcp, [pos for pos in positions if pos in {"QB", "RB", "WR", "TE"}], season)
    schedule_cache: dict[str, list[dict[str, Any]]] = {}
    result: dict[str, Any] = {"season": season, "limit": limit, "positions": {}}
    for position in positions:
        rows = []
        for rank, candidate in enumerate(by_position.get(position, [])[:limit], start=1):
            team = candidate.team or (candidate.player_id if position == "DEF" else None)
            if team not in schedule_cache:
                schedule_cache[str(team)] = team_schedule(mcp, str(team), season) if team else []
            weekly = weekly_projection(candidate, schedule_cache.get(str(team), []), defense_rankings)
            rows.append(
                {
                    "rank": rank,
                    "player": candidate.as_dict(),
                    "weekly_breakdown": weekly,
                    "weekly_total": round(sum(game["projected_ppr"] for game in weekly), 2),
                }
            )
        result["positions"][position] = rows
    return result


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Top {report['limit']} Available Players By Position",
        "",
        "Weekly projections are normalized to each player's season projection. Schedule is a light modifier, not the main draft-score driver.",
        "",
    ]
    for position, rows in report["positions"].items():
        lines.append(f"## {position}")
        lines.append("")
        for row in rows:
            player = row["player"]
            lines.append(
                f"### {row['rank']}. {player['name']} ({player['team'] or 'FA'}) - "
                f"{player['projected_season_points']} PPR, {player['projected_fp_per_game']} fp/g, score {player['score']}"
            )
            lines.append("")
            lines.append("| Week | Opp | H/A | Proj | Note |")
            lines.append("|---:|---|---|---:|---|")
            for game in row["weekly_breakdown"]:
                lines.append(
                    f"| {game['week']} | {game['opponent']} | {game['home_away']} | "
                    f"{game['projected_ppr']} | {game['matchup_note']} |"
                )
            lines.append("")
    return "\n".join(lines)

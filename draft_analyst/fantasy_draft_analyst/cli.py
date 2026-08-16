from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import DraftAnalyst, format_recommendation
from .config import Settings
from .server import run_server
from .weekly import markdown_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local fantasy football draft analyst.")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("recommend", help="Recommend my next Sleeper draft pick.")
    rec.add_argument("--manual-state", help="JSON fallback with draft/picks/players/my_slot.")
    rec.add_argument("--json", action="store_true", help="Print raw JSON.")

    sub.add_parser("health", help="Check local NFL MCP/Ollama/Abacus configuration.")

    serve = sub.add_parser("serve", help="Run local web UI/API.")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)

    top = sub.add_parser("top-weekly", help="Generate top players by position with weekly game projections.")
    top.add_argument("--positions", default="QB,RB,WR,TE,K,DEF", help="Comma-separated positions.")
    top.add_argument("--limit", type=int, default=30)
    top.add_argument("--season", type=int, default=2026)
    top.add_argument("--json-out", default="outputs/top_weekly.json")
    top.add_argument("--md-out", default="outputs/top_weekly.md")

    args = parser.parse_args(argv)
    settings = Settings.from_env()
    analyst = DraftAnalyst(settings)

    try:
        if args.command == "recommend":
            result = analyst.recommend(args.manual_state)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(format_recommendation(result))
            return 0
        if args.command == "health":
            print(json.dumps(analyst.health(), indent=2))
            return 0
        if args.command == "serve":
            run_server(analyst, host=args.host or settings.analyst_host, port=args.port or settings.analyst_port)
            return 0
        if args.command == "top-weekly":
            positions = [position.strip().upper() for position in args.positions.split(",") if position.strip()]
            report = analyst.position_report(positions=positions, limit=args.limit, season=args.season)
            json_path = Path(args.json_out)
            md_path = Path(args.md_out)
            json_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(json.dumps(report, indent=2))
            md_path.write_text(markdown_report(report))
            print(f"Wrote {json_path}")
            print(f"Wrote {md_path}")
            return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH="$PWD/draft_analyst${PYTHONPATH:+:$PYTHONPATH}" python3 -m fantasy_draft_analyst.cli recommend "$@"

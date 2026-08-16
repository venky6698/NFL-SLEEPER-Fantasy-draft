#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

read -r -p "Sleeper draft ID: " sleeper_draft_id
read -r -p "Your draft slot: " my_draft_slot
read -r -s -p "Abacus API key: " abacus_api_key
printf "\n"

python3 - "$sleeper_draft_id" "$my_draft_slot" "$abacus_api_key" <<'PY'
from pathlib import Path
import sys

updates = {
    "SLEEPER_DRAFT_ID": sys.argv[1].strip(),
    "MY_DRAFT_SLOT": sys.argv[2].strip(),
    "ABACUS_API_KEY": sys.argv[3].strip().strip('"').strip("'").strip().removeprefix("**").removesuffix("**").replace("\\_", "_"),
    "NFL_MCP_URL": "http://localhost:9000/mcp",
    "ABACUS_BASE_URL": "https://routellm.abacus.ai/v1",
    "ABACUS_MODEL": "route-llm",
    "OLLAMA_MODEL": "llama3:latest",
}

path = Path(".env")
lines = path.read_text().splitlines()
seen = set()
out = []
for line in lines:
    if "=" not in line or line.lstrip().startswith("#"):
        out.append(line)
        continue
    key = line.split("=", 1)[0].strip()
    if key in updates:
        out.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        out.append(line)

for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")

path.write_text("\n".join(out) + "\n")
print(".env updated")
PY

echo "Checking the analyst..."
draft-analyst health

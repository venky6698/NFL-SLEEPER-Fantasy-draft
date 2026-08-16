# NFL-SLEEPER Fantasy Draft

Local fantasy football live draft analyst for Sleeper drafts, built on top of an existing `gtonic/nfl_mcp` Docker server.

The analyst reads your live Sleeper draft, gathers NFL/fantasy context through NFL MCP, computes an explainable candidate score, and sends the structured candidate set to Abacus RouteLLM for final reasoning. If Abacus is unavailable, it falls back to a local Ollama model, then to the deterministic local scoring model.

## What It Does

- Connects to Sleeper live/mock drafts.
- Reads league settings, draft slot, picks, rosters, available players, recent positional runs, and roster construction.
- Uses NFL MCP tools for draft board data, injuries, strength of schedule, defense rankings, coaching context, draft picks, and league context when available.
- Scores candidates using projected season points, fantasy points per game, floor/ceiling, value over replacement, positional scarcity, tier pressure, roster fit, injury risk, opportunity, team context, and probability the player survives to your next pick.
- Uses Abacus RouteLLM as the primary reasoning layer through `ABACUS_API_KEY`.
- Supports Ollama fallback without requiring new large model downloads.
- Provides a CLI and a local browser UI/API.
- Supports manual JSON draft state fallback when direct Sleeper polling is not possible.

## Requirements

- macOS with Python 3.11+
- Docker Desktop running `gtonic/nfl_mcp`
- Sleeper draft ID and your draft slot
- Abacus RouteLLM API key
- Optional: Ollama with a small local model such as `llama3:latest`

Apple Silicon M4 with 24GB RAM is supported. The app does not require any huge local model downloads.

## Start NFL MCP

Run your existing NFL MCP server:

```bash
docker run --rm -p 9000:9000 ghcr.io/gtonic/nfl_mcp:latest
```

The analyst expects:

```text
NFL_MCP_URL=http://localhost:9000/mcp
```

## Install the Analyst

From this repo:

```bash
python3 -m pip install -e .
```

Verify:

```bash
draft-analyst health
```

## Configure

Create `.env`:

```bash
cp .env.example .env
```

Then edit:

```text
SLEEPER_DRAFT_ID=your_draft_id
MY_DRAFT_SLOT=your_slot_number
ABACUS_API_KEY=your_abacus_key
```

Or use the local prompt script. It hides the Abacus key while typing:

```bash
./scripts/configure_local.sh
```

Do not commit `.env`.

## Abacus RouteLLM

The app uses Abacus RouteLLM’s OpenAI-compatible Chat Completions API:

```text
ABACUS_BASE_URL=https://routellm.abacus.ai/v1
ABACUS_MODEL=route-llm
```

Enterprise Abacus workspaces can use:

```text
ABACUS_BASE_URL=https://<workspace>.abacus.ai/v1
```

## Recommend My Next Pick

```bash
draft-analyst recommend
```

JSON output:

```bash
draft-analyst recommend --json
```

Convenience script:

```bash
./scripts/recommend.sh
```

## Run Local UI/API

```bash
draft-analyst serve
```

Open:

```text
http://127.0.0.1:8787
```

Endpoints:

```text
GET /api/health
GET /api/recommend
```

## Manual Draft-State Fallback

Direct Sleeper polling is preferred. If you only have a screenshot, transcribe the current board into JSON:

```json
{
  "draft_id": "manual",
  "my_slot": 4,
  "draft": {
    "draft_id": "manual",
    "status": "manual",
    "settings": {
      "teams": 12,
      "rounds": 16,
      "slots_qb": 1,
      "slots_rb": 2,
      "slots_wr": 2,
      "slots_te": 1,
      "slots_flex": 1
    },
    "metadata": {
      "scoring_type": "ppr"
    }
  },
  "picks": [
    {
      "player_id": "1",
      "draft_slot": 1,
      "pick_no": 1,
      "metadata": {
        "position": "RB"
      }
    }
  ],
  "players": {}
}
```

Then:

```bash
draft-analyst recommend --manual-state path/to/manual.json
```

## Tests

```bash
python3 -m pytest -q
```

## Security

- Secrets are loaded from `.env`.
- `.env` is ignored by Git.
- The app never needs your Abacus key pasted into chat.
- The NFL MCP server is preserved and used over local HTTP.

## More Setup Detail

See [docs/SETUP.md](docs/SETUP.md).

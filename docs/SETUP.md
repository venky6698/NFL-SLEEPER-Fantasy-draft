# Local Fantasy Football Draft Analyst

This project is a standalone client for your existing `gtonic/nfl_mcp` Docker server. It does not modify or replace the NFL MCP container.

## 1. Start NFL MCP

```bash
docker run --rm -p 9000:9000 ghcr.io/gtonic/nfl_mcp:latest
```

The analyst expects:

```text
NFL_MCP_URL=http://localhost:9000/mcp
```

## 2. Configure the Analyst

```bash
cp .env.example .env
```

Edit `.env`:

```text
SLEEPER_DRAFT_ID=your_draft_id
MY_DRAFT_SLOT=your_slot_number
ABACUS_API_KEY=your_abacus_key
```

Do not commit `.env` and do not paste the key into chat.

Or run the local prompt-based setup:

```bash
./scripts/configure_local.sh
```

Abacus RouteLLM is OpenAI-compatible per the current official docs:

```text
ABACUS_BASE_URL=https://routellm.abacus.ai/v1
ABACUS_MODEL=route-llm
```

Enterprise Abacus workspaces use:

```text
ABACUS_BASE_URL=https://<workspace>.abacus.ai/v1
```

## 3. Run a Recommendation

```bash
python3 -m pip install -e .
python3 -m fantasy_draft_analyst.cli recommend
```

JSON output:

```bash
python3 -m fantasy_draft_analyst.cli recommend --json
```

## 4. Run the Local UI/API

```bash
python3 -m fantasy_draft_analyst.cli serve
```

Open:

```text
http://127.0.0.1:8787
```

API endpoints:

```text
GET /api/health
GET /api/state
GET /api/recommend
```

The browser UI keeps a local live draft board and refreshes Sleeper every minute by default. Change this cadence in `.env`:

```text
LIVE_SYNC_INTERVAL_SECONDS=60
```

Recommendations use that live snapshot and exclude all drafted player IDs before sending the candidate set to Abacus.

## 5. Mock-Draft Test

Use a Sleeper mock draft ID in `.env`, then run:

```bash
python3 -m fantasy_draft_analyst.cli health
python3 -m fantasy_draft_analyst.cli recommend
```

The analyst reads live picks directly from Sleeper, checks NFL MCP for richer context when the tools are available, scores candidates locally, sends the structured candidate set to Abacus when `ABACUS_API_KEY` is set, and falls back to Ollama or local deterministic output if needed.

## 6. Manual/Screenshot Fallback

Direct Sleeper polling is preferred. If you only have a screenshot, transcribe the board into a JSON file:

```json
{
  "draft_id": "manual",
  "my_slot": 4,
  "draft": {
    "draft_id": "manual",
    "status": "manual",
    "settings": {"teams": 12, "rounds": 16, "slots_qb": 1, "slots_rb": 2, "slots_wr": 2, "slots_te": 1, "slots_flex": 1},
    "metadata": {"scoring_type": "ppr"}
  },
  "picks": [
    {"player_id": "1", "draft_slot": 1, "pick_no": 1, "metadata": {"position": "RB"}}
  ],
  "players": {}
}
```

Then:

```bash
python3 -m fantasy_draft_analyst.cli recommend --manual-state path/to/manual.json
```

## Apple Silicon M4 / 24GB

No large local downloads are required. Abacus is the primary reasoning layer. Ollama is optional; use an already-installed small model such as `llama3:latest`, `llama3.1:8b`, or `qwen2.5:7b`. Avoid 70B-class local models on 24GB RAM.

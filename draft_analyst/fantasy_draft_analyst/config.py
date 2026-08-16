from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def clean_env_value(value: str) -> str:
    value = value.strip().strip('"').strip("'").strip()
    while len(value) >= 2 and value.startswith("**") and value.endswith("**"):
        value = value[2:-2].strip()
    value = value.replace("\\_", "_")
    return value


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = clean_env_value(value)
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    nfl_mcp_url: str = "http://localhost:9000/mcp"
    sleeper_draft_id: str | None = None
    sleeper_league_id: str | None = None
    sleeper_username: str | None = None
    my_draft_slot: int | None = None
    abacus_api_key: str | None = None
    abacus_base_url: str = "https://routellm.abacus.ai/v1"
    abacus_model: str = "route-llm"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3:latest"
    enable_vegas: bool = False
    analyst_host: str = "127.0.0.1"
    analyst_port: int = 8787

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        slot = os.getenv("MY_DRAFT_SLOT")
        port = os.getenv("ANALYST_PORT")
        return cls(
            nfl_mcp_url=os.getenv("NFL_MCP_URL", cls.nfl_mcp_url),
            sleeper_draft_id=os.getenv("SLEEPER_DRAFT_ID") or None,
            sleeper_league_id=os.getenv("SLEEPER_LEAGUE_ID") or None,
            sleeper_username=os.getenv("SLEEPER_USERNAME") or None,
            my_draft_slot=int(slot) if slot else None,
            abacus_api_key=os.getenv("ABACUS_API_KEY") or None,
            abacus_base_url=os.getenv("ABACUS_BASE_URL", cls.abacus_base_url).rstrip("/"),
            abacus_model=os.getenv("ABACUS_MODEL", cls.abacus_model),
            ollama_url=os.getenv("OLLAMA_URL", cls.ollama_url).rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", cls.ollama_model),
            enable_vegas=os.getenv("ENABLE_VEGAS", "false").lower() in {"1", "true", "yes", "on"},
            analyst_host=os.getenv("ANALYST_HOST", cls.analyst_host),
            analyst_port=int(port) if port else cls.analyst_port,
        )

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_env_file(path: Path | None = None) -> None:
    """Load simple KEY=VALUE entries without replacing process-level configuration."""
    path = path or ENV_FILE
    if not path.is_file():
        return
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not ENV_KEY.fullmatch(key):
            raise ValueError(f"Invalid .env entry at {path}:{line_number}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    database_url: str
    input_pack_path: Path
    max_input_chars: int
    ollama_context_tokens: int
    groq_model: str
    groq_api_key: str | None = field(repr=False)
    analyst_token: str | None = field(repr=False)
    reviewer_token: str | None = field(repr=False)

    @classmethod
    def from_environment(cls) -> "Settings":
        load_env_file()
        return cls(
            database_url=os.getenv(
                "KASPARRO_DATABASE_URL",
                f"sqlite:///{(PROJECT_ROOT / 'backend' / 'kasparro.db').as_posix()}",
            ),
            input_pack_path=Path(
                os.getenv("KASPARRO_INPUT_PACK", str(PROJECT_ROOT))
            ).resolve(),
            max_input_chars=int(os.getenv("KASPARRO_MAX_INPUT_CHARS", "20000")),
            ollama_context_tokens=int(
                os.getenv("KASPARRO_OLLAMA_CONTEXT_TOKENS", "16384")
            ),
            groq_model=os.getenv("KASPARRO_GROQ_MODEL", "openai/gpt-oss-20b"),
            groq_api_key=os.getenv("GROQ_API_KEY") or None,
            analyst_token=os.getenv("KASPARRO_ANALYST_TOKEN") or None,
            reviewer_token=os.getenv("KASPARRO_REVIEWER_TOKEN") or None,
        )


from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    database_url: str
    input_pack_path: Path
    max_input_chars: int

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            database_url=os.getenv(
                "KASPARRO_DATABASE_URL",
                f"sqlite:///{(PROJECT_ROOT / 'backend' / 'kasparro.db').as_posix()}",
            ),
            input_pack_path=Path(
                os.getenv("KASPARRO_INPUT_PACK", str(PROJECT_ROOT))
            ).resolve(),
            max_input_chars=int(os.getenv("KASPARRO_MAX_INPUT_CHARS", "20000")),
        )


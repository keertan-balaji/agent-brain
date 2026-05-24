"""Brain config: env-var loader + future brain_config table reader."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BrainConfig:
    """Static config from environment. Dynamic config lives in the brain_config DB table."""

    db_url: str
    vault_path: Path
    brain_subdir: str

    @property
    def brain_path(self) -> Path:
        return self.vault_path / self.brain_subdir


def load_config() -> BrainConfig:
    db_url = os.environ.get(
        "BRAIN_DB_URL",
        "postgresql+psycopg://brain:brain_dev_password@127.0.0.1:5433/brain",
    )
    vault = Path(os.environ.get("OBSIDIAN_VAULT", str(Path.home() / "Documents/ObsidianVault")))
    subdir = os.environ.get("BRAIN_SUBDIR", "Agent-Brain")
    return BrainConfig(db_url=db_url, vault_path=vault, brain_subdir=subdir)

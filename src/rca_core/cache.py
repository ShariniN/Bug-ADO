from __future__ import annotations

import json
from pathlib import Path

from rca_core.config import Config


def cache_path(cfg: Config, bug_id: int) -> Path:
    return cfg.cache_dir / f"{bug_id}.json"


def read_cache(cfg: Config, bug_id: int) -> dict:
    p = cache_path(cfg, bug_id)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def write_cache(cfg: Config, bug_id: int, data: dict) -> Path:
    p = cache_path(cfg, bug_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    merged = {**read_cache(cfg, bug_id), **data}
    p.write_text(json.dumps(merged, indent=1), encoding="utf-8")
    return p

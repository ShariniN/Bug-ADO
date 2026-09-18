from __future__ import annotations

from rca_core.ado_client import AdoClient
from rca_core.config import Config
from rca_core.operations.setup import read_status, write_status


def detect_bug_type(cfg: Config, client: AdoClient) -> str:
    if cfg.bug_type:
        return cfg.bug_type
    cached = read_status(cfg).get("bug_type")
    if cached:
        return cached
    names = client.list_work_item_types()
    lower = {n.lower(): n for n in names}
    chosen = lower.get("bug") or lower.get("issue") or next((n for n in names if "bug" in n.lower()), "Bug")
    write_status(cfg, bug_type=chosen)
    return chosen

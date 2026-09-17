from __future__ import annotations

from rca_core.ado_client import AdoClient
from rca_core.config import Config
from rca_core.errors import guarded
from rca_core.fields import validate_field_map


@guarded
def fields_op(cfg: Config, client: AdoClient) -> dict:
    available = client.bug_fields()
    issues = validate_field_map(cfg.fields, available)
    return {"fields": available, "issues": issues, "ok": not issues}

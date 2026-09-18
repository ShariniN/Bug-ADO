from __future__ import annotations

import json

from rca_core.ado_client import AdoClient
from rca_core.config import Config
from rca_core.errors import guarded
from rca_core.fields import SECTION_LABELS, validate_field_map


@guarded
def fields_op(cfg: Config, client: AdoClient, auto_map: bool = False) -> dict:
    available = client.bug_fields()
    issues = validate_field_map(cfg.fields, available)
    accepted: dict[str, str] = {}
    if auto_map and issues:
        by_name = {f["name"].strip().lower(): f["referenceName"] for f in available}
        by_ref = {f["referenceName"].lower(): f["referenceName"] for f in available}
        for issue in issues:
            label = SECTION_LABELS[issue["section"]].lower()
            ref = by_name.get(label) or by_ref.get(f"custom.{label.replace(' ', '')}")
            if ref:
                accepted[issue["section"]] = ref
        if accepted:
            from rca_core.operations.setup import save_config
            save_config(cfg, fields=accepted)
            cfg.fields.update(accepted)
            issues = validate_field_map(cfg.fields, available)
    (cfg.home / "status.json").parent.mkdir(parents=True, exist_ok=True)
    (cfg.home / "status.json").write_text(json.dumps({"fields_ok": not issues}), encoding="utf-8")
    return {"fields": available, "issues": issues, "ok": not issues, "auto_mapped": accepted}

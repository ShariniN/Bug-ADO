from __future__ import annotations

from rca_core.ado_client import AdoClient
from rca_core.config import Config
from rca_core.defect_type import detect_bug_type
from rca_core.errors import guarded
from rca_core.fields import SECTION_LABELS, validate_field_map


@guarded
def fields_op(cfg: Config, client: AdoClient, auto_map: bool = False) -> dict:
    available = client.bug_fields(detect_bug_type(cfg, client))
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
    from rca_core.operations.setup import write_status
    write_status(cfg, fields_ok=not issues)
    return {"fields": available, "issues": issues, "ok": not issues, "auto_mapped": accepted}

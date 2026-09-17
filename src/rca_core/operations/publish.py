from __future__ import annotations

from rca_core.ado_client import AdoClient
from rca_core.config import Config
from rca_core.errors import RcaError, guarded
from rca_core.fields import SECTION_KEYS


@guarded
def publish(bug_id: int, sections: dict[str, str], cfg: Config, client: AdoClient, dry_run: bool = True) -> dict:
    unknown = [k for k in sections if k not in SECTION_KEYS]
    if unknown:
        raise RcaError("field_missing", f"Unknown section key(s): {', '.join(unknown)}.",
                       f"Use only these keys: {', '.join(SECTION_KEYS)}.")
    unmapped = [k for k in sections if not cfg.fields.get(k)]
    if unmapped:
        raise RcaError("field_missing", f"No field mapped for section(s): {', '.join(unmapped)}.",
                       "Run /rca-setup or add the mapping under [fields] in ~/.rca/config.toml.")

    available = {f["referenceName"]: f for f in client.bug_fields()}
    patch: dict[str, str] = {}
    for key, value in sections.items():
        ref = cfg.fields[key]
        if ref not in available:
            raise RcaError("field_missing", f"Field {ref} (section {key}) does not exist on the Bug type.",
                           "Run /rca-setup to re-map the field.")
        allowed = available[ref].get("allowedValues") or []
        if allowed and value not in allowed:
            raise RcaError("field_type_mismatch", f"Value '{value}' is not allowed for {ref}.",
                           f"Use one of: {', '.join(allowed)}.")
        if available[ref].get("type") == "string" and len(value) > 255:
            raise RcaError("field_type_mismatch",
                           f"Value for {ref} (section {key}) is {len(value)} chars; single-line string fields hold at most 255.",
                           "Shorten the text or map this section to an HTML/plain-text (multi-line) field.")
        patch[ref] = value

    if dry_run:
        return {"dry_run": True, "patch": patch}
    res = client.patch_work_item(bug_id, patch)
    return {"dry_run": False, **res}

from __future__ import annotations

import json


def _scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(str(v))  # JSON string escapes are valid TOML basic-string escapes


def dumps(data: dict) -> str:
    """Minimal TOML writer: top-level scalars, then one level of tables with scalar values."""
    top = [f"{k} = {_scalar(v)}" for k, v in data.items() if not isinstance(v, dict)]
    out = ["\n".join(top)] if top else []
    for name, table in data.items():
        if isinstance(table, dict):
            lines = [f"[{name}]"] + [f"{json.dumps(k) if not k.replace('_', '').replace('-', '').isalnum() else k} = {_scalar(v)}"
                                     for k, v in table.items()]
            out.append("\n".join(lines))
    return "\n\n".join(out) + "\n"

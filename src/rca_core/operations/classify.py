from __future__ import annotations

from rca_core.cache import read_cache
from rca_core.classifier import classify
from rca_core.config import Config
from rca_core.errors import RcaError, guarded
from rca_core.models import Culprit, TraceResult, WorkItemRef, to_dict


def trace_from_dict(d: dict) -> TraceResult:
    culprits = []
    for c in d.get("culprits", []):
        c = dict(c)
        c["work_items"] = [WorkItemRef(**w) for w in c.get("work_items", [])]
        c["parent_chain"] = [WorkItemRef(**w) for w in c.get("parent_chain", [])]
        culprits.append(Culprit(**c))
    return TraceResult(bug_id=d["bug_id"], repo=d.get("repo", ""), culprits=culprits,
                       evidence=d.get("evidence", []), confidence_notes=d.get("confidence_notes", []))


@guarded
def classify_op(bug_id: int, cfg: Config, trace_data: dict | None = None) -> dict:
    data = trace_data or read_cache(cfg, bug_id).get("trace")
    if not data:
        raise RcaError("fetch_first", f"No trace cached for bug {bug_id}.", "Run rca_fetch then rca_trace first.")
    return to_dict(classify(trace_from_dict(data), cfg))

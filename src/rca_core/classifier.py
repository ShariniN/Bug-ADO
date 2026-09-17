from __future__ import annotations

from rca_core.config import Config
from rca_core.models import Proposal, TraceResult, WorkItemRef
from rca_core.versions import parse_version

LEGACY, FEATURE, NON_FEATURE = "Legacy Bug", "Feature Bug", "Non-Feature Bug"


def _feature_in_chain(chain: list[WorkItemRef]) -> WorkItemRef | None:
    for wi in chain:
        if wi.type.lower() == "feature":
            return wi
    return None


def classify(trace: TraceResult, cfg: Config) -> Proposal:
    if not trace.culprits:
        return Proposal(NON_FEATURE, "low", "No culprit commit could be traced from the fix diff.", True)

    top = trace.culprits[0]
    cutoff = parse_version(cfg.legacy_cutoff)

    if top.earliest_version is not None and parse_version(top.earliest_version) <= cutoff:
        conf = "medium" if top.lines <= 1 else "high"
        return Proposal(
            LEGACY, conf,
            f"Culprit {top.sha[:8]} is contained in release {top.earliest_version}, which is <= {cfg.legacy_cutoff}.",
            False,
        )

    feature = _feature_in_chain(top.parent_chain) or _feature_in_chain(top.work_items)
    if feature is not None:
        if cfg.current_pi and feature.iteration.startswith(cfg.current_pi):
            return Proposal(
                FEATURE, "high",
                f"Culprit {top.sha[:8]} traces to Feature {feature.id} '{feature.title}' in current PI iteration '{feature.iteration}'.",
                False,
            )
        elif not cfg.current_pi:
            return Proposal(
                FEATURE, "low",
                f"Culprit {top.sha[:8]} traces to Feature {feature.id} '{feature.title}' (iteration '{feature.iteration}'), but the current PI is not configured or does not match.",
                True,
            )
        # cfg.current_pi is set but doesn't match - fall through to Non-Feature

    where = f"release {top.earliest_version}" if top.earliest_version else "no release branch (unreleased)"
    if feature is not None:
        return Proposal(
            NON_FEATURE, "medium",
            f"Culprit {top.sha[:8]} traces to Feature {feature.id} '{feature.title}' (iteration '{feature.iteration}'), but its iteration is outside the current PI '{cfg.current_pi}'.",
            True,
        )
    return Proposal(
        NON_FEATURE, "medium",
        f"Culprit {top.sha[:8]} first appears in {where}, above the legacy cutoff, and its work items do not reach a Feature.",
        True,
    )

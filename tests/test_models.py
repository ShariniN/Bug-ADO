from rca_core.models import Culprit, Proposal, TraceResult, WorkItemRef, to_dict
from rca_core.errors import RcaError, guarded


def test_to_dict_round_trips_nested_dataclasses():
    wi = WorkItemRef(id=1, type="Feature", title="Payroll", iteration="Proj\\PI-12")
    c = Culprit(sha="a" * 40, author="Jane", date="2024-01-01", subject="add", lines=3,
                pr_id=7, pr_title="PR", work_items=[wi], parent_chain=[wi],
                release_branches=["release/9.5"], earliest_version="9.5")
    t = TraceResult(bug_id=5, repo="Web", culprits=[c], evidence=["x"], confidence_notes=[])
    d = to_dict(t)
    assert d["culprits"][0]["work_items"][0]["type"] == "Feature"
    assert d["culprits"][0]["earliest_version"] == "9.5"


def test_proposal_defaults():
    p = Proposal(classification="Legacy Bug", confidence="high", reason="r")
    assert p.needs_confirmation is False


def test_guarded_converts_rca_error_to_dict():
    @guarded
    def boom():
        raise RcaError("no_pat", "PAT missing", "Set ADO_PAT")

    assert boom() == {"error": {"code": "no_pat", "message": "PAT missing", "fix": "Set ADO_PAT"}}


def test_guarded_passes_through_result():
    @guarded
    def ok():
        return {"a": 1}

    assert ok() == {"a": 1}


def test_rca_error_to_dict_omits_debug_when_unset():
    assert "debug" not in RcaError("x", "m", "f").to_dict()["error"]


def test_rca_error_to_dict_includes_debug_when_set():
    assert RcaError("x", "m", "f", debug="d").to_dict()["error"]["debug"] == "d"

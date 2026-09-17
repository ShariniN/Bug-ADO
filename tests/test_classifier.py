from rca_core.classifier import classify
from rca_core.config import load_config
from rca_core.models import Culprit, TraceResult, WorkItemRef


def cfg(tmp_path, current_pi=""):
    c = load_config(user_path=tmp_path / "none.toml", env={})
    c.current_pi = current_pi
    return c


def culprit(**kw):
    base = dict(sha="a" * 40, author="A", date="2024-01-01", subject="s", lines=10)
    base.update(kw)
    return Culprit(**base)


def trace(*culprits, notes=None):
    return TraceResult(bug_id=1, repo="R", culprits=list(culprits), evidence=[], confidence_notes=notes or [])


def test_legacy_when_earliest_version_at_or_below_cutoff(tmp_path):
    p = classify(trace(culprit(earliest_version="9.5", release_branches=["release/9.5"])), cfg(tmp_path))
    assert p.classification == "Legacy Bug"
    assert p.confidence == "high"
    assert p.needs_confirmation is False


def test_legacy_equal_to_cutoff(tmp_path):
    p = classify(trace(culprit(earliest_version="9.6")), cfg(tmp_path))
    assert p.classification == "Legacy Bug"


def test_legacy_medium_confidence_when_single_line(tmp_path):
    p = classify(trace(culprit(earliest_version="9.0", lines=1)), cfg(tmp_path))
    assert p.confidence == "medium"


def test_feature_when_chain_reaches_feature_in_current_pi(tmp_path):
    feat = WorkItemRef(id=9, type="Feature", title="F", iteration="Proj\\PI-12\\Sprint 1")
    p = classify(trace(culprit(earliest_version="10.1", parent_chain=[feat])), cfg(tmp_path, "Proj\\PI-12"))
    assert p.classification == "Feature Bug"
    assert p.confidence == "high"


def test_feature_low_confidence_when_pi_unknown(tmp_path):
    feat = WorkItemRef(id=9, type="Feature", title="F", iteration="Proj\\PI-12")
    p = classify(trace(culprit(earliest_version="10.1", parent_chain=[feat])), cfg(tmp_path, ""))
    assert p.classification == "Feature Bug"
    assert p.confidence == "low"
    assert p.needs_confirmation is True


def test_non_feature_otherwise(tmp_path):
    p = classify(trace(culprit(earliest_version="10.1")), cfg(tmp_path, "Proj\\PI-12"))
    assert p.classification == "Non-Feature Bug"
    assert p.confidence == "medium"
    assert p.needs_confirmation is True


def test_no_culprits_is_non_feature_low(tmp_path):
    p = classify(trace(), cfg(tmp_path))
    assert p.classification == "Non-Feature Bug"
    assert p.confidence == "low"
    assert p.needs_confirmation is True

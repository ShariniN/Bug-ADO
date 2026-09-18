import os

import pytest

from rca_core.ado_client import AdoClient, RequestsTransport
from rca_core.config import load_config
from rca_core.operations.fetch import fetch
from rca_core.operations.trace import trace

pytestmark = pytest.mark.skipif(os.environ.get("RCA_LIVE") != "1", reason="set RCA_LIVE=1 and RCA_LIVE_BUG=<id> to run against the real org")


def test_live_fetch_returns_bug_and_hunks():
    cfg = load_config()
    client = AdoClient(cfg.org_url, cfg.project, RequestsTransport(cfg.pat()))
    out = fetch(int(os.environ["RCA_LIVE_BUG"]), cfg, client)
    assert "error" not in out, out
    assert out["bug"]["title"] and out["files"]


def test_live_trace_finds_a_culprit():
    cfg = load_config()
    client = AdoClient(cfg.org_url, cfg.project, RequestsTransport(cfg.pat()))
    bug_id = int(os.environ["RCA_LIVE_BUG"])
    fetch_out = fetch(bug_id, cfg, client)
    assert "error" not in fetch_out, fetch_out
    out = trace(bug_id, cfg, client)
    assert "error" not in out, out
    assert out["culprits"]

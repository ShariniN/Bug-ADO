import os

import pytest

from rca_core.ado_client import AdoClient, RequestsTransport
from rca_core.config import load_config
from rca_core.operations.fetch import fetch

pytestmark = pytest.mark.skipif(os.environ.get("RCA_LIVE") != "1", reason="set RCA_LIVE=1 and RCA_LIVE_BUG=<id> to run against the real org")


def test_live_fetch_returns_bug_and_hunks():
    cfg = load_config()
    client = AdoClient(cfg.org_url, cfg.project, RequestsTransport(cfg.pat()))
    out = fetch(int(os.environ["RCA_LIVE_BUG"]), cfg, client)
    assert "error" not in out, out
    assert out["bug"]["title"] and out["files"]

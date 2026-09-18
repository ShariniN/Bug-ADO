from rca_core.ado_client import AdoClient
from rca_core.config import load_config
from rca_core.defect_type import detect_bug_type
from tests.ado_routes import types_route
from tests.conftest import FakeTransport

ORG, PROJ = "https://dev.azure.com/acme", "Acme"


def cfg(tmp_path):
    c = load_config(user_path=tmp_path / "c.toml", env={})
    c.home = tmp_path
    return c


def client(routes):
    return AdoClient(ORG, PROJ, FakeTransport(routes))


def test_override_wins_without_network(tmp_path):
    c = cfg(tmp_path)
    c.bug_type = "Defect"
    assert detect_bug_type(c, client({})) == "Defect"


def test_prefers_bug_when_present(tmp_path):
    assert detect_bug_type(cfg(tmp_path), client(types_route(["Epic", "Bug"]))) == "Bug"


def test_falls_back_to_issue(tmp_path):
    assert detect_bug_type(cfg(tmp_path), client(types_route(["Epic", "Issue"]))) == "Issue"


def test_falls_back_to_name_containing_bug(tmp_path):
    assert detect_bug_type(cfg(tmp_path), client(types_route(["Defect Bug Item"]))) == "Defect Bug Item"


def test_empty_types_defaults_to_bug(tmp_path):
    assert detect_bug_type(cfg(tmp_path), client(types_route([]))) == "Bug"


def test_second_call_served_from_status_json(tmp_path):
    c = cfg(tmp_path)
    t = FakeTransport(types_route(["Epic", "Issue"]))
    cl = AdoClient(ORG, PROJ, t)
    assert detect_bug_type(c, cl) == "Issue"
    assert detect_bug_type(c, cl) == "Issue"
    type_calls = [call for call in t.calls if call[0] == "GET" and "workitemtypes?" in call[1]]
    assert len(type_calls) == 1

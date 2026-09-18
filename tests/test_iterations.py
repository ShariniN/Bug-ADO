from rca_core.iterations import current_pi

TREE = {"name": "Acme", "children": [
    {"name": "PI-13", "attributes": {"startDate": "2026-05-01T00:00:00Z", "finishDate": "2026-07-31T00:00:00Z"}, "children": []},
    {"name": "PI-14", "attributes": {"startDate": "2026-08-01T00:00:00Z", "finishDate": "2026-10-31T00:00:00Z"}, "children": [
        {"name": "Sprint 1", "attributes": {"startDate": "2026-08-01T00:00:00Z", "finishDate": "2026-08-14T00:00:00Z"}},
        {"name": "Sprint 4", "attributes": {"startDate": "2026-09-12T00:00:00Z", "finishDate": "2026-09-25T00:00:00Z"}}]},
    {"name": "Backlog", "children": []},
]}


def test_pi_with_dates_is_found():
    assert current_pi(TREE, "2026-09-18") == "Acme\\PI-14"


def test_pi_without_dates_is_inferred_from_sprint():
    tree = {"name": "Acme", "children": [{"name": "PI-14", "children": [
        {"name": "Sprint 4", "attributes": {"startDate": "2026-09-12T00:00:00Z", "finishDate": "2026-09-25T00:00:00Z"}}]}]}
    assert current_pi(tree, "2026-09-18") == "Acme\\PI-14"


def test_no_current_iteration():
    assert current_pi(TREE, "2027-01-01") is None

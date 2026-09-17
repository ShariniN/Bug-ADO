from types import SimpleNamespace

from rca_core.update_check import current_version, newer_tag


def fake_runner(stdout, returncode=0):
    def run(*a, **k):
        return SimpleNamespace(stdout=stdout, returncode=returncode)
    return run


LS = "abc\trefs/tags/v0.1.0\nabd\trefs/tags/v0.2.1\nabe\trefs/tags/junk\n"


def test_newer_tag_found():
    assert newer_tag("git@x/y.git", "0.1.0", runner=fake_runner(LS)) == "0.2.1"


def test_no_newer_tag():
    assert newer_tag("git@x/y.git", "0.2.1", runner=fake_runner(LS)) is None


def test_empty_url_or_failure_returns_none():
    assert newer_tag("", "0.1.0", runner=fake_runner(LS)) is None
    assert newer_tag("u", "0.1.0", runner=fake_runner("", returncode=128)) is None


def test_current_version_is_string():
    assert isinstance(current_version(), str)

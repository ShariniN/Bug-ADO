from rca_core.versions import earliest_version, parse_version, version_from_branch

PAT = r"release/(\d+\.\d+)"


def test_parse_version_numeric_tuple():
    assert parse_version("9.6") == (9, 6)
    assert parse_version("10.1.2") == (10, 1, 2)
    assert parse_version("9.6") < parse_version("10.1")


def test_version_from_branch_handles_remote_prefix():
    assert version_from_branch("origin/release/10.1", PAT) == "10.1"
    assert version_from_branch("release/9.5", PAT) == "9.5"
    assert version_from_branch("main", PAT) is None


def test_earliest_version_sorts_numerically():
    assert earliest_version(["release/10.1", "origin/release/9.5", "main"], PAT) == "9.5"
    assert earliest_version(["main", "develop"], PAT) is None

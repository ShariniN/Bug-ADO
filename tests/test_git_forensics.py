from rca_core.diffparse import parse_unified_diff
from rca_core.git_forensics import blame_hunks
from rca_core.models import Hunk


def test_diff_and_blame_find_culprit_ignoring_whitespace(git_repo):
    repo, sha = git_repo
    diff = repo.diff(sha["ws"], sha["fix_src"])
    files = parse_unified_diff(diff)
    assert files[0].path == "pay.py"
    counts = blame_hunks(repo, sha["ws"], files[0].hunks)
    assert counts == {sha["culprit"]: 1}


def test_commit_info_fields(git_repo):
    repo, sha = git_repo
    info = repo.commit_info(sha["culprit"])
    assert info["sha"] == sha["culprit"]
    assert info["subject"] == "culprit: make b nullable"
    assert info["author"] == "T"
    assert len(info["date"]) == 10  # YYYY-MM-DD


def test_branches_containing(git_repo):
    repo, sha = git_repo
    assert "release/10.1" in repo.branches_containing(sha["culprit"])
    assert "release/9.5" not in repo.branches_containing(sha["culprit"])
    assert "release/9.5" in repo.branches_containing(sha["c1"])


def test_merged_pr_id_from_history(git_repo):
    repo, sha = git_repo
    assert repo.merged_pr_id_from_history(sha["fix_src"], "merged") == 42
    # culprit was committed directly on main; the later fix merge must NOT be attributed to it
    assert repo.merged_pr_id_from_history(sha["culprit"], "merged") is None


def test_merge_base_and_current_branch(git_repo):
    repo, sha = git_repo
    assert repo.current_branch() == "main"
    assert repo.merge_base("bugfix/1", "main") == sha["ws"]
    assert repo.has_ref("release/9.5") and not repo.has_ref("nope")


def test_pure_addition_hunk_blames_three_surrounding_lines(git_repo):
    repo, sha = git_repo
    h = Hunk(old_path="pay.py", new_path="pay.py", old_start=2, old_len=0,
             new_start=3, new_len=1, text="+    c = 1")
    counts = blame_hunks(repo, sha["ws"], [h])
    assert counts == {sha["c1"]: 2, sha["culprit"]: 1}

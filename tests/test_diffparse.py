from rca_core.diffparse import cap_hunks, is_whitespace_only, parse_unified_diff, removed_old_lines

DIFF = """diff --git a/src/pay.py b/src/pay.py
index 1111111..2222222 100644
--- a/src/pay.py
+++ b/src/pay.py
@@ -10,4 +10,5 @@ def calc():
     a = 1
-    b = None
-    return a + b
+    b = 0
+    return a + b
+    # done
diff --git a/new.txt b/new.txt
new file mode 100644
--- /dev/null
+++ b/new.txt
@@ -0,0 +1 @@
+hello
diff --git a/gone.txt b/gone.txt
deleted file mode 100644
--- a/gone.txt
+++ /dev/null
@@ -1 +0,0 @@
-bye
diff --git a/img.png b/img.png
Binary files a/img.png and b/img.png differ
"""


def test_parse_files_and_hunks():
    files = parse_unified_diff(DIFF)
    assert [(f.path, f.change) for f in files] == [
        ("src/pay.py", "modify"), ("new.txt", "add"), ("gone.txt", "delete"), ("img.png", "modify"),
    ]
    h = files[0].hunks[0]
    assert (h.old_start, h.old_len, h.new_start, h.new_len) == (10, 4, 10, 5)
    assert h.old_path == "src/pay.py"
    assert h.text.splitlines()[0] == "     a = 1"
    assert files[3].hunks == []


def test_removed_old_lines_are_exact():
    h = parse_unified_diff(DIFF)[0].hunks[0]
    assert removed_old_lines(h) == [11, 12]


def test_whitespace_only_hunk_detected():
    files = parse_unified_diff(
        "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1,2 +1,2 @@\n-a  =1\n-b\n+a = 1\n+b\n"
    )
    assert is_whitespace_only(files[0].hunks[0]) is True
    assert is_whitespace_only(parse_unified_diff(DIFF)[0].hunks[0]) is False


def test_cap_hunks_truncates_and_flags():
    files = parse_unified_diff(DIFF)
    capped, truncated = cap_hunks(files, max_bytes=40)
    assert truncated is True
    assert sum(len(h.text) for f in capped for h in f.hunks) <= 40
    full, t2 = cap_hunks(files, max_bytes=100_000)
    assert t2 is False and full == files

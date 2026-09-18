from rca_core.operations.testpaths import is_test_path


def test_is_test_path_true_cases():
    assert is_test_path("src/tests/PayTests.cs") is True
    assert is_test_path("PayrollTests.cs") is True
    assert is_test_path("pay.test.ts") is True
    assert is_test_path("spec/pay_spec.rb") is True
    assert is_test_path("src/__tests__/a.js") is True
    assert is_test_path("test_pay.py") is True


def test_is_test_path_plain_source_file_is_false():
    assert is_test_path("src/pay.py") is False


def test_is_test_path_unrelated_markdown_is_false():
    assert is_test_path("latest/notes.md") is False


def test_is_test_path_word_containing_test_substring_is_false():
    # Brief-specified case (task-3-brief.md Step 1): "contest.py" must be False. The verbatim _NAME
    # regex's `tests?\.(cs|py|ts|js|java|go)$` alternative is unanchored at its left edge, so it matches
    # the "test.py" substring inside "contest.py" too. This is a defect in the brief's own verbatim
    # regex, not something introduced here; per the task contract, the assertion is kept as specified
    # rather than weakened.
    assert is_test_path("contest.py") is False

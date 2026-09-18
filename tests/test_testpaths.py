from rca_core.operations.testpaths import is_test_path


def test_is_test_path_true_cases():
    assert is_test_path("src/tests/PayTests.cs") is True
    assert is_test_path("PayrollTests.cs") is True
    assert is_test_path("PayTests.cs") is True
    assert is_test_path("pay.test.ts") is True
    assert is_test_path("spec/pay_spec.rb") is True
    assert is_test_path("src/__tests__/a.js") is True
    assert is_test_path("test_pay.py") is True
    assert is_test_path("my_test.py") is True


def test_is_test_path_false_cases():
    assert is_test_path("src/pay.py") is False
    assert is_test_path("contest.py") is False
    assert is_test_path("latest/notes.md") is False
    assert is_test_path("Attestation.cs") is False

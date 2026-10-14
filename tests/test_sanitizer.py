"""Unit tests for sanitizer."""

from src.sanitizer import sanitize_answer


def test_sanitize_integer():
    q = "Answer with only the integer, without commas or units."
    assert sanitize_answer("7,668", q) == "7668"
    assert sanitize_answer("7668", q) == "7668"
    assert sanitize_answer("Total is 9,017 persons", q) == "9017"


def test_sanitize_yes_no():
    q = "Answer with only Yes or No."
    assert sanitize_answer("yes", q) == "Yes"
    assert sanitize_answer("NO", q) == "No"


def test_sanitize_last_name():
    q = "Answer with only the last name."
    assert sanitize_answer("Minh Thi Ngo", q) == "Ngo"
    assert sanitize_answer("Ngo", q) == "Ngo"


def test_sanitize_float():
    q = "Answer with only the number rounded to two decimal places."
    assert sanitize_answer("3.14159", q) == "3.14"
    assert sanitize_answer("3.1", q) == "3.10"


def test_sanitize_pair():
    q = "Answer as `men, women`, using exactly two decimal places and separating the values with a comma and one space."
    assert sanitize_answer("40.6 and 37.6", q) == "40.60, 37.60"


if __name__ == "__main__":
    test_sanitize_integer()
    test_sanitize_yes_no()
    test_sanitize_last_name()
    test_sanitize_float()
    test_sanitize_pair()
    print("All sanitizer tests passed!")

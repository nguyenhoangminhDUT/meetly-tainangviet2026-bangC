"""Comprehensive Test Suite for Meetly Spreadsheet QA Pipeline."""

import sys
from pathlib import Path
import pandas as pd

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.normalizer import load_normalized_workbook, make_unique_columns, clean_cell_value, is_num_cell
from src.sanitizer import sanitize_answer, strip_thousands_separators
from src.schema_builder import build_schema_summary, extract_keywords
from src.solver import execute_code_safely


def test_unique_columns():
    cols = ["col", "col", "col_1", "col"]
    uniq = make_unique_columns(cols)
    assert len(uniq) == len(set(uniq))
    assert uniq[0] == "col"
    assert uniq[2] == "col_1"


def test_is_num_cell():
    assert is_num_cell(42) is True
    assert is_num_cell(3.14) is True
    assert is_num_cell("58,176") is True
    assert is_num_cell("$1,402") is True
    assert is_num_cell("10%") is True
    assert is_num_cell("(1.5)") is True
    assert is_num_cell("Not a number") is False
    assert is_num_cell("..") is False
    assert is_num_cell("-") is False


def test_strip_thousands_separators():
    assert strip_thousands_separators("7,668") == "7668"
    assert strip_thousands_separators("1,094,431") == "1094431"
    assert strip_thousands_separators("2020, 9743") == "2020, 9743"
    assert strip_thousands_separators("34,282, 118,705") == "34282, 118705"


def test_multilingual_sanitizer():
    # Exactly one decimal place
    assert sanitize_answer("4.71", "Answer with only the number using exactly one decimal place.") == "4.7"
    assert sanitize_answer("50", "Chỉ trả lời bằng số với đúng một chữ số thập phân.") == "50.0"
    assert sanitize_answer("10.42", "Répondez uniquement par le nombre avec une décimale, sans le symbole %.") == "10.4"
    assert sanitize_answer("19.12", "只回答数字，保留一位小数。") == "19.1"

    # Exactly two decimal places
    assert sanitize_answer("1.2", "Answer with only the number using exactly two decimal places.") == "1.20"
    assert sanitize_answer("14.2", "소수점 둘째 자리까지, % 기호 없이 숫자만 답하십시오.") == "14.20"
    assert sanitize_answer("40.6 and 37.6", "Answer as `men, women`, using exactly two decimal places and separating the values with a comma and one space.") == "40.60, 37.60"

    # Exactly three decimal places
    assert sanitize_answer("29.4921", "Answer with only the number using exactly three decimal places.") == "29.492"
    assert sanitize_answer("0.8709", "rounded to three decimal places") == "0.871"

    # Only the Year
    assert sanitize_answer("The year was 1954", "Identify the year when... Answer with only the year.") == "1954"
    assert sanitize_answer("2013", "in which year did the... Answer with only the year.") == "2013"

    # Integers without commas
    assert sanitize_answer("27,124 dollars", "Chỉ trả lời bằng số nguyên, không có dấu phẩy.") == "27124"
    assert sanitize_answer("2020 and 9743", "Answer as `year, decrease`, separated by a comma and one space, as integers without commas or units.") == "2020, 9743"
    assert sanitize_answer("1955, 62,170", "Answer as `year, total employed`, separated by a comma and one space, with the total as an integer without commas or units.") == "1955, 62170"

    # Yes / No
    assert sanitize_answer("yes", "Answer with only Yes or No.") == "Yes"
    assert sanitize_answer("no", "Answer with only Yes or No.") == "No"

    # Only last name
    assert sanitize_answer("Minh Thi Ngo", "Answer with only the last name.") == "Ngo"


def test_schema_builder_keywords():
    q = "What is the unadjusted percent change for Housing and Food?"
    kws = extract_keywords(q)
    assert "housing" in kws
    assert "food" in kws
    assert "unadjusted" in kws


def test_sandboxed_code_execution():
    code = """
def solve(dfs):
    df = dfs['test']
    return df['A'].sum()
"""
    dfs = {'test': pd.DataFrame({'A': [10, 20, 30]})}
    res, err = execute_code_safely(code, dfs)
    assert err is None
    assert res == 60


def test_all_public_workbooks_normalization():
    for d in ["data/data_public_1/xlsx_files", "data/Public data 2/xlsx_files"]:
        p = Path(d)
        if not p.exists():
            continue
        for f in sorted(p.glob("*.xlsx")):
            if f.name.startswith("~$"):
                continue
            dfs = load_normalized_workbook(f)
            assert len(dfs) > 0, f"No sheets returned for {f.name}"
            for sname, df in dfs.items():
                assert not df.empty, f"Empty DataFrame for {f.name}::{sname}"
                # Guarantee column uniqueness
                assert len(df.columns) == len(set(df.columns)), f"Duplicate columns in {f.name}::{sname}"


if __name__ == "__main__":
    print("Running test suite...")
    test_unique_columns()
    test_is_num_cell()
    test_strip_thousands_separators()
    test_multilingual_sanitizer()
    test_schema_builder_keywords()
    test_sandboxed_code_execution()
    test_all_public_workbooks_normalization()
    print(">>> ALL 7 TEST SUITES PASSED FLAWLESSLY! <<<")

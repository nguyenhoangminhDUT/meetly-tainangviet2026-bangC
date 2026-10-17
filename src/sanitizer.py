"""Strict Output Sanitizer for Exact Match evaluation across multilingual spreadsheet QA queries."""

import re
from typing import Any, List, Optional, Tuple, Union


def strip_thousands_separators(text: str) -> str:
    """Removes thousands separator commas (e.g. 7,668 -> 7668, 1,094,431 -> 1094431) while preserving comma-separated lists (e.g. 2020, 9743)."""
    while re.search(r"(\d),(\d{3})(?!\d)", text):
        text = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", text)
    return text


def sanitize_answer(raw_answer: Any, query: str = "") -> str:
    """Sanitize and format raw answer to conform to strict Exact Match requirements."""
    if raw_answer is None:
        return ""

    # Convert tuple or list to string elements
    if isinstance(raw_answer, (list, tuple)):
        formatted_items = []
        for x in raw_answer:
            formatted_items.append(str(x).strip("'\" "))
        text = ", ".join(formatted_items)
    else:
        text = str(raw_answer).strip()

    # Strip markdown formatting (bold, backticks, codeblocks)
    text = re.sub(r"^\*\*(.*?)\*\*$", r"\1", text)
    text = re.sub(r"^`{1,3}(?:[a-zA-Z]*\n)?(.*?)\n?`{1,3}$", r"\1", text, flags=re.DOTALL).strip()
    text = re.sub(r"[\r\n]+", " ", text).strip()
    text = " ".join(text.split())

    # Pre-clean thousands separator commas inside numbers
    text = strip_thousands_separators(text)

    q_lower = query.lower()

    # Strip hierarchical delimiter ' | ' if one part is already mentioned in query or is redundant section header
    if " | " in text and not any(k in q_lower for k in ["both", "order", "rank", "list", "descending", "ascending"]):
        parts = text.split(" | ")
        if any(p.strip().lower() in q_lower for p in parts[1:]):
            text = parts[0].strip()
        elif any(p.strip().lower() in q_lower for p in parts[:-1]):
            text = parts[-1].strip()
        elif len(parts) == 2 and any(re.search(r"\b(19\d\d|20\d\d)\b", p) for p in parts[1:]):
            text = parts[1].strip()

    # =========================================================================
    # 1. Yes / No queries (English, Vietnamese, French, Chinese, Korean)
    # =========================================================================
    if any(k in q_lower for k in ["yes or no", "yes/no", "có hoặc không", "oui ou non", "是否", "是或否", "예 또는 아니오"]):
        t_low = text.lower()
        if any(w in t_low for w in ["yes", "true", "oui", "có", "đúng", "是", "예"]):
            return "Yes"
        if any(w in t_low for w in ["no", "false", "non", "không", "sai", "否", "아니오"]):
            return "No"

    # =========================================================================
    # 2. Only Last Name queries
    # =========================================================================
    if any(k in q_lower for k in ["only the last name", "last name only", "chỉ họ"]):
        tokens = text.split()
        if tokens:
            return tokens[-1].strip(",. ")

    # =========================================================================
    # 3. Only the Year queries (e.g. 1953, 1954, 2013, 2020)
    # =========================================================================
    if any(k in q_lower for k in ["only the year", "only the fiscal year", "fiscal year as an integer", "chỉ trả lời bằng năm", "년도만"]):
        years = re.findall(r"\b(19\d\d|20\d\d)\b", text)
        if years:
            return years[0]

    # =========================================================================
    # 4. Strict Decimal Place Rounding (1, 2, or 3 decimal places)
    # =========================================================================
    is_one_dec = any(k in q_lower for k in [
        "one decimal place", "1 decimal place", "one decimal", "with a decimal",
        "một chữ số thập phân", "1 chữ số thập phân", "une décimale", "1 décimale",
        "소수점 한 자리", "소수점 첫째 자리", "一位小数", "保留一位小数"
    ])

    is_two_dec = any(k in q_lower for k in [
        "two decimal places", "2 decimal places", "rounded to two decimal places",
        "hai chữ số thập phân", "2 chữ số thập phân", "deux décimales", "2 décimales",
        "소수점 둘째 자리", "소수점 두 자리", "两位小数", "保留两位小数"
    ])

    is_three_dec = any(k in q_lower for k in [
        "three decimal places", "3 decimal places", "rounded to three decimal places",
        "ba chữ số thập phân", "3 chữ số thập phân", "trois décimales", "3 décimales",
        "소수점 셋째 자리", "三位小数", "保留三位小数"
    ])

    target_decimals = 1 if is_one_dec else (2 if is_two_dec else (3 if is_three_dec else None))

    if target_decimals is not None:
        fmt = f"{{:.{target_decimals}f}}"

        # Check if query expects multiple numbers (e.g. `report both rates`, `for both groups`, `separating by comma`)
        if any(k in q_lower for k in ["both", "two rates", "two numbers", "report both", "separating", "for each"]):
            num_tokens = re.findall(r"-?\d+\.?\d*", text.replace(",", " "))
            if len(num_tokens) >= 2:
                try:
                    return ", ".join(fmt.format(float(p)) for p in num_tokens)
                except ValueError:
                    pass

        # Check if composite query with comma (e.g. `group, difference`, `size class, gap`)
        if "," in text:
            parts = [p.strip() for p in text.split(",")]
            # Only format all parts if the query explicitly asks for both/all rates/numbers
            format_all = any(k in q_lower for k in ["both", "two rates", "two numbers", "report both", "separating", "for each"])
            formatted_parts = []
            for p in parts:
                p_clean = p.replace("$", "").replace("%", "").strip()
                if format_all:
                    num_match = re.search(r"-?\d+\.?\d*", p_clean)
                    if num_match:
                        try:
                            formatted_parts.append(fmt.format(float(num_match.group(0))))
                        except ValueError:
                            formatted_parts.append(p)
                    else:
                        formatted_parts.append(p)
                else:
                    # Only format parts that are floating point numbers (have a decimal point)
                    if re.fullmatch(r"-?\d+\.\d+", p_clean):
                        try:
                            formatted_parts.append(fmt.format(float(p_clean)))
                        except ValueError:
                            formatted_parts.append(p)
                    else:
                        formatted_parts.append(p)
            return ", ".join(formatted_parts)

        # Standalone numeric value
        num_match = re.search(r"-?\d+\.?\d*", text)
        if num_match:
            try:
                val = float(num_match.group(0))
                return fmt.format(val)
            except ValueError:
                pass

    # =========================================================================
    # 5. Integer Queries (without commas or units)
    # =========================================================================
    is_integer_query = any(k in q_lower for k in [
        "without commas or units", "without thousands separators", "only the integer",
        "as integers", "số nguyên", "không có dấu phẩy", "without commas inside the number",
        "entier", "nombre entier", "정수", "整数"
    ])

    if is_integer_query:
        # If text has comma, check if it's a composite with text (e.g. table_1, 1307 or Mexican, 16)
        if "," in text:
            parts = [p.strip() for p in text.split(",")]
            has_text_part = any(re.search(r"[a-zA-Z\u00C0-\u024F\u1EA0-\u1EF9]", p) for p in parts)
            if has_text_part:
                formatted_parts = []
                for p in parts:
                    p_clean = p.replace("$", "").replace("%", "").strip()
                    if re.fullmatch(r"-?\d[\d,]*", p_clean):
                        formatted_parts.append(p_clean.replace(",", ""))
                    else:
                        formatted_parts.append(p)
                return ", ".join(formatted_parts)

        # Check if query expects multiple integers (e.g. `year, decrease` or `two integers`)
        nums = re.findall(r"-?\d+", text)
        if len(nums) >= 2 and any(k in q_lower for k in [
            "two integers", "year, decrease", "year, total", "year, increase",
            "order `", "as two integers", "as integers without"
        ]):
            return ", ".join(nums[:2])

        if "," in text:
            return ", ".join(p.replace("$", "").replace("%", "").replace(",", "").strip() for p in text.split(","))

        # Single integer
        cleaned = text.replace("$", "").replace("%", "").strip()
        single_nums = re.findall(r"-?\d+", cleaned)
        if single_nums:
            return single_nums[0]

    # =========================================================================
    # 6. Candidate Ranking / Listing
    # =========================================================================
    if "rank the following" in q_lower or ("descending order" in q_lower and ":" in query):
        m = re.search(r":\s*([^.]+)", query)
        if m:
            raw_cands = m.group(1).replace("and ", "").split(",")
            cands = [c.strip() for c in raw_cands if c.strip()]
            items = [it.strip(" '\"[]") for it in text.split(",")]
            mapped_items = []
            for it in items:
                matched = False
                for c in cands:
                    if c.lower() in it.lower():
                        mapped_items.append(c)
                        matched = True
                        break
                if not matched:
                    mapped_items.append(it)
            text = ", ".join(mapped_items)

    # Clean superfluous quotes, periods, and commas at boundaries
    text = text.strip('"\' ,')
    return text

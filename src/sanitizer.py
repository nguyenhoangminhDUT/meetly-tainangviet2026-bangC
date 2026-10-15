"""Strict Output Sanitizer for Exact Match evaluation."""

import re
from typing import Any


def sanitize_answer(raw_answer: Any, query: str = "") -> str:
    """Sanitize and format raw answer to conform to strict Exact Match requirements."""
    if raw_answer is None:
        return ""

    text = str(raw_answer).strip()

    # Strip markdown formatting
    text = re.sub(r"^\*\*(.*?)\*\*$", r"\1", text)
    text = re.sub(r"^`{1,3}(?:[a-zA-Z]*\n)?(.*?)\n?`{1,3}$", r"\1", text, flags=re.DOTALL).strip()

    q_lower = query.lower()

    # Case 1: Yes / No queries
    if "yes or no" in q_lower or "yes/no" in q_lower:
        if "yes" in text.lower():
            return "Yes"
        if "no" in text.lower():
            return "No"

    # Case 2: Only last name
    if "only the last name" in q_lower or "last name only" in q_lower:
        # If full name is returned e.g. "Minh Thi Ngo", extract last token
        tokens = text.split()
        if tokens:
            return tokens[-1].strip(",. ")

    # Case 3: Only the integer, without commas or units
    if "without commas or units" in q_lower or "without thousands separators" in q_lower:
        # Check if query expects multiple integers (e.g. "two integers in the order ... separated by a comma and one space")
        if "two integers" in q_lower or "separated by a comma and one space" in q_lower:
            parts = re.findall(r"\b\d[\d,]*\b", text)
            if len(parts) >= 2:
                clean_parts = [p.replace(",", "") for p in parts[:2]]
                return ", ".join(clean_parts)
        # Single integer
        cleaned = text.replace(",", "").replace("$", "").replace("%", "").strip()
        nums = re.findall(r"-?\d+", cleaned)
        if nums:
            return nums[0]

    # Case 4: Rounded to two decimal places
    if "two decimal places" in q_lower or "rounded to two decimal places" in q_lower:
        # Check if query expects multiple floats separated by a comma
        parts = re.findall(r"-?\d+\.?\d*", text.replace(",", " "))
        if "separated with a comma" in q_lower or "separated by a comma" in q_lower:
            if len(parts) >= 2:
                try:
                    formatted = [f"{float(p):.2f}" for p in parts]
                    return ", ".join(formatted)
                except ValueError:
                    pass
        nums = re.findall(r"-?\d+\.?\d*", text)
        if nums:
            try:
                val = float(nums[0])
                return f"{val:.2f}"
            except ValueError:
                pass

    # Clean newlines and superfluous whitespace
    text = " ".join(text.split())

    # Case 5: Ranking or listing candidate categories mentioned in query
    if "rank the following" in q_lower or ("descending order" in q_lower and ":" in query):
        m = re.search(r":\s*([^.]+)", query)
        if m:
            raw_cands = m.group(1).replace("and ", "").split(",")
            cands = [c.strip() for c in raw_cands if c.strip()]
            items = [it.strip() for it in text.split(",")]
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

    # Clean superfluous trailing periods or quotes
    text = text.strip('"\' ')
    return text

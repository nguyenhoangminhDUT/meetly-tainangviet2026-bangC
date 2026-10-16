"""Schema Builder: Generates information-dense, compact schema and semantic context for LLM prompt."""

import re
from typing import Dict, List, Optional
import pandas as pd


def extract_keywords(query: str) -> List[str]:
    """Extracts informative query terms (excluding common stopwords and formatting keywords)."""
    stopwords = {
        'the', 'a', 'an', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
        'is', 'are', 'was', 'were', 'what', 'which', 'who', 'how', 'many', 'much', 'did',
        'does', 'than', 'from', 'between', 'answer', 'only', 'using', 'exactly', 'separated',
        'comma', 'space', 'integer', 'decimal', 'place', 'places', 'units', 'number',
        'table', 'sheet', 'row', 'column', 'trong', 'các', 'cho', 'của', 'là', 'bao', 'nhiêu',
        'chỉ', 'trả', 'lời', 'bằng', 'số', 'parmi', 'quel', 'est', 'pour'
    }
    # Extract words including hyphenated or alphanumeric tokens
    tokens = re.findall(r"[\w\u00C0-\u1EF9\u4E00-\u9FFF\uAC00-\uD7AF]+(?:-[\w]+)?", query.lower())
    keywords = [t for t in tokens if len(t) >= 3 and t not in stopwords]
    return keywords


def build_sheet_overview(sheet_name: str, df: pd.DataFrame, query: str = "") -> str:
    """Builds a compact summary for a single sheet, including columns, categories, and keyword-matched rows."""
    lines = [f"Sheet '{sheet_name}' ({df.shape[0]} rows, {df.shape[1]} cols):"]

    # 1. Column names
    cols = list(df.columns)
    lines.append(f"Columns: {cols}")

    if df.empty:
        return "\n".join(lines)

    # 2. Check if Col 0 is Indent Level
    first_col_name = str(cols[0]).lower()
    is_indent_col = "indent" in first_col_name or (
        df.shape[1] > 1 and df.iloc[:, 0].dropna().astype(str).str.fullmatch(r"\d+").all()
    )

    cat_col_idx = 1 if is_indent_col else 0
    cat_col_name = cols[cat_col_idx]
    if is_indent_col:
        lines.append(f"Note: Column 0 is Indent Level (0=top-level, 1=child, 2=grandchild). Item names are in Column 1 ('{cat_col_name}').")

    # 3. Sample row categories
    u_labels = [str(x) for x in df.iloc[:, cat_col_idx].dropna().unique() if str(x) != 'nan']
    sample_labels = u_labels[:30]
    lines.append(f"Row categories ({cat_col_name}): {sample_labels}")

    # 4. Keyword matching context for grounded answering
    keywords = extract_keywords(query)
    matching_rows = []
    if keywords:
        for idx in range(len(df)):
            row_str = " ".join(str(v).lower() for v in df.iloc[idx].values if pd.notna(v))
            if any(kw in row_str for kw in keywords):
                # Format compact row snippet
                val_snippet = [f"{cols[c]}: {df.iloc[idx, c]}" for c in range(min(df.shape[1], 6)) if pd.notna(df.iloc[idx, c])]
                matching_rows.append(f"  * [Row {idx}] {df.iloc[idx, cat_col_idx]} -> {', '.join(val_snippet[:4])}")
                if len(matching_rows) >= 5:
                    break

    if matching_rows:
        lines.append("Relevant rows matching query terms:")
        lines.extend(matching_rows)

    return "\n".join(lines)


def build_schema_summary(dfs: Dict[str, pd.DataFrame], query: str = "") -> str:
    """Builds a unified schema and data context summary across all sheets in the workbook."""
    summaries = []
    for sname, df in dfs.items():
        summaries.append(build_sheet_overview(sname, df, query))
    return "\n\n".join(summaries)

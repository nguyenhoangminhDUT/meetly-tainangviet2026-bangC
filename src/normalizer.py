"""Excel Semantic Normalizer: Unwraps merged cells and flattens hierarchical headers."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import openpyxl
import pandas as pd


def load_normalized_workbook(file_path: str | Path) -> Dict[str, pd.DataFrame]:
    """Loads an .xlsx file, resolves all merged cells, and converts each sheet to a normalized DataFrame."""
    wb = openpyxl.load_workbook(file_path, data_only=True)
    sheets_data: Dict[str, pd.DataFrame] = {}

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        df = normalize_worksheet(ws)
        if df is not None and not df.empty:
            sheets_data[sheet_name] = df

    return sheets_data


import re

def clean_cell_value(val: Any) -> Any:
    if isinstance(val, str):
        val = re.sub(r'-\s*\n\s*', '', val)
        val = re.sub(r'\s*\n\s*', ' ', val)
        val = re.sub(r'\s+', ' ', val).strip()
    return val


def normalize_worksheet(ws: openpyxl.worksheet.worksheet.Worksheet) -> Optional[pd.DataFrame]:
    """Converts a single openpyxl worksheet into a cleanly structured pandas DataFrame with unmerged cells."""
    if ws.max_row is None or ws.max_column is None:
        return None

    # Step 1: Read all raw cells into a 2D matrix
    max_r = ws.max_row
    max_c = ws.max_column
    grid: List[List[Any]] = [[None for _ in range(max_c)] for _ in range(max_r)]

    for r in range(1, max_r + 1):
        for c in range(1, max_c + 1):
            val = ws.cell(r, c).value
            grid[r - 1][c - 1] = clean_cell_value(val)

    # Step 2: Propagate merged cell values across the entire merged range
    for merged_range in list(ws.merged_cells.ranges):
        min_col, min_row, max_col, max_row = merged_range.bounds
        top_left_val = grid[min_row - 1][min_col - 1]
        for r in range(min_row, max_row + 1):
            for c in range(min_col, max_col + 1):
                grid[r - 1][c - 1] = top_left_val

    # Convert to base DataFrame
    raw_df = pd.DataFrame(grid)
    raw_df = raw_df.dropna(how="all").dropna(how="all", axis=1)
    if raw_df.empty:
        return None

    raw_df.reset_index(drop=True, inplace=True)
    return clean_and_headerize(raw_df)


def clean_and_headerize(df: pd.DataFrame) -> pd.DataFrame:
    """Removes metadata rows, merges multi-level headers into column names, and propagates section headers."""
    # Step 1: Strip metadata prefix rows
    start = 0
    for r in range(min(5, len(df))):
        s_val = ' '.join(str(x) for x in df.iloc[r] if str(x) != 'nan')
        if any(k in s_val for k in ['HOUSEHOLD DATA', '[In thousands]', '[Numbers in thousands]']):
            start = r + 1
    sub_df = df.iloc[start:].reset_index(drop=True)

    # Step 2: Detect first actual data or section row
    first_data = 1
    for r in range(min(7, len(sub_df))):
        row_vals = sub_df.iloc[r]
        nums = []
        for x in row_vals:
            s_num = str(x).strip()
            if re.match(r'^-?\d+(\.\d+)?$', s_num):
                nums.append(float(s_num))
        # Header rows may contain years (1900-2100) or units; data rows contain actual values
        non_year_nums = [n for n in nums if n < 1900 or n > 2100]
        other_vals = [x for x in row_vals.iloc[1:] if pd.notna(x) and str(x).strip() not in ['', 'nan', 'None']]
        if len(non_year_nums) >= 2 or (r > 0 and len(other_vals) == 0):
            first_data = r
            break

    # Step 3: Combine hierarchical headers into composite column names
    cols = []
    for c in range(sub_df.shape[1]):
        parts = []
        for hr in range(first_data):
            v = str(sub_df.iloc[hr, c]).strip()
            if v and v != 'nan' and v != 'None' and v not in parts:
                parts.append(v)
        cols.append(' | '.join(parts) if parts else f'Col_{c}')

    data_df = sub_df.iloc[first_data:].reset_index(drop=True)
    data_df.columns = cols
    data_df = data_df.dropna(how="all")

    # Step 4: Propagate section headers in column 0
    current_section = ''
    clean_rows = []
    for idx in range(len(data_df)):
        row = data_df.iloc[idx].copy()
        val0 = str(row.iloc[0]).strip()
        other_vals = [x for x in row.iloc[1:] if pd.notna(x) and str(x).strip() not in ['', 'nan', 'None']]
        # Section header row has non-empty col 0 but no other column values
        if len(other_vals) == 0 and val0 not in ['', 'nan', 'None'] and not any(k in val0 for k in ['Footnotes:', 'NOTE:']):
            current_section = val0
        else:
            if current_section and not val0.startswith(current_section) and not any(k in val0 for k in ['Footnotes:', 'NOTE:']):
                row.iloc[0] = f'{current_section} | {val0}'
            clean_rows.append(row)

    if clean_rows:
        return pd.DataFrame(clean_rows).reset_index(drop=True)
    return data_df

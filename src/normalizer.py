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
            grid[r - 1][c - 1] = ws.cell(r, c).value

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
    return raw_df

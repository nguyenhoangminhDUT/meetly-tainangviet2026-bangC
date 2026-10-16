import sys
sys.path.insert(0, ".")
import openpyxl
from pathlib import Path
import pandas as pd
from src.normalizer import load_normalized_workbook
import time

xlsx_dir = Path("data/data_public_1/xlsx_files")
files = sorted([f for f in xlsx_dir.glob("*.xlsx") if not f.name.startswith("~$")])

print(f"Total excel files: {len(files)}")
print("=" * 95)

audit_data = []
start_all = time.time()

for f in files:
    wb = openpyxl.load_workbook(f, data_only=True)
    sheets = wb.sheetnames
    total_merged = sum(len(wb[s].merged_cells.ranges) for s in sheets)
    
    t0 = time.time()
    norm_dfs = load_normalized_workbook(f)
    t_norm = time.time() - t0
    
    first_sheet = sheets[0]
    ws = wb[first_sheet]
    
    has_footnotes = False
    has_merged_headers = False
    max_indent = 0
    
    for row in ws.iter_rows():
        for cell in row:
            val = cell.value
            if val and any(k in str(val) for k in ["Footnotes:", "NOTE:", "(1)", "[1]", "1/", "2/"]):
                has_footnotes = True
            if cell.alignment and cell.alignment.indent and cell.alignment.indent > max_indent:
                max_indent = cell.alignment.indent
                
    df_norm = norm_dfs.get(first_sheet, pd.DataFrame())
    sample_cols = list(df_norm.columns)[:3]
    
    audit_data.append({
        "file": f.name,
        "sheets": len(sheets),
        "sheet_names": sheets,
        "raw_shape": (ws.max_row, ws.max_column),
        "norm_shape": df_norm.shape,
        "merged_ranges": total_merged,
        "max_indent": max_indent,
        "has_footnotes": has_footnotes,
        "sample_col": sample_cols[1] if len(sample_cols) > 1 else "",
        "norm_time_s": round(t_norm, 3)
    })

total_time = time.time() - start_all

for a in audit_data:
    print(f"{a['file']:<12} | Sheets: {a['sheets']} | Raw: {str(a['raw_shape']):<10} | Norm: {str(a['norm_shape']):<10} | Merged: {a['merged_ranges']:<3} | Indent: {a['max_indent']} | FN: {str(a['has_footnotes']):<5} | Time: {a['norm_time_s']}s")

print("=" * 95)
print(f"Total normalizer runtime across 10 files: {total_time:.3f}s")

print("\n--- DETAILED INSPECTION OF HEADERS & COLUMNS ---")
for a in audit_data:
    print(f"\n[{a['file']}]")
    print(f"  Sheets: {a['sheet_names']}")
    print(f"  Sample Normalized Column: {a['sample_col']}")

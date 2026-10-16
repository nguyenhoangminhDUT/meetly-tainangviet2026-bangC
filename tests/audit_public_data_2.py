"""Empirical Audit and Benchmarking Script for Public Data 1 and Public Data 2."""

import sys
import time
import json
from pathlib import Path
import openpyxl
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.normalizer import load_normalized_workbook
from src.sanitizer import sanitize_answer
from src.schema_builder import build_schema_summary


def run_comprehensive_audit():
    print("=" * 80)
    print("MEETLY TABLE QA: COMPREHENSIVE PIPELINE AUDIT & BENCHMARK")
    print("=" * 80)

    datasets = [
        ("Public Data 1", Path("data/data_public_1/xlsx_files"), Path("data/data_public_1/queries.json"), Path("data/data_public_1/sample_submission.csv")),
        ("Public Data 2", Path("data/Public data 2/xlsx_files"), Path("data/Public data 2/queries.json"), Path("data/Public data 2/answers.json")),
    ]

    summary_stats = []

    for name, xlsx_dir, queries_path, ans_path in datasets:
        print(f"\n>>> AUDITING DATASET: {name}")
        t0 = time.time()
        files = sorted([f for f in xlsx_dir.glob("*.xlsx") if not f.name.startswith("~$")])

        total_sheets = 0
        total_cells_unmerged = 0
        total_rows_normalized = 0
        file_metrics = []

        for f in files:
            wb = openpyxl.load_workbook(f, data_only=True)
            merged_count = sum(len(wb[s].merged_cells.ranges) for s in wb.sheetnames)
            total_cells_unmerged += merged_count

            tf0 = time.time()
            dfs = load_normalized_workbook(f)
            tf_duration = time.time() - tf0

            for sname, df in dfs.items():
                total_sheets += 1
                total_rows_normalized += df.shape[0]
                file_metrics.append({
                    "file": f.name,
                    "sheet": sname,
                    "shape": df.shape,
                    "merged_ranges": merged_count,
                    "norm_time": round(tf_duration, 4)
                })

        norm_time_total = time.time() - t0

        # Query and Ground truth analysis
        with open(queries_path, "r", encoding="utf-8") as qf:
            queries = json.load(qf)

        gt_map = {}
        if ans_path.suffix.lower() == ".json":
            with open(ans_path, "r", encoding="utf-8") as af:
                ans_data = json.load(af)
            gt_map = {str(a["id"]): str(a["answer"]) for a in ans_data}
        else:
            adf = pd.read_csv(ans_path)
            id_col = "id" if "id" in adf.columns else adf.columns[0]
            ans_col = "answer" if "answer" in adf.columns else adf.columns[1]
            gt_map = {str(r[id_col]): str(r[ans_col]) for _, r in adf.iterrows()}

        # Multilingual distribution
        lang_dist = {"English": 0, "Vietnamese": 0, "French": 0, "Korean": 0, "Chinese": 0}
        for q in queries:
            txt = q["query"]
            if any(k in txt for k in ["chăm sóc", "trình độ", "bao nhiêu", "thu nhập"]):
                lang_dist["Vietnamese"] += 1
            elif any(k in txt for k in ["autochtones", "Parmi", "femmes", "écart"]):
                lang_dist["French"] += 1
            elif any(k in txt for k in ["법원", "감소", "소수점"]):
                lang_dist["Korean"] += 1
            elif any(k in txt for k in ["对于", "人群", "百分点"]):
                lang_dist["Chinese"] += 1
            else:
                lang_dist["English"] += 1

        summary_stats.append({
            "dataset": name,
            "files": len(files),
            "sheets": total_sheets,
            "merged_ranges": total_cells_unmerged,
            "total_rows": total_rows_normalized,
            "norm_time_total": round(norm_time_total, 3),
            "queries": len(queries),
            "ground_truth_count": len(gt_map),
            "lang_dist": lang_dist,
            "file_metrics": file_metrics
        })

        print(f"  * Workbooks: {len(files)} files | Sheets: {total_sheets} sheets")
        print(f"  * Merged ranges resolved: {total_cells_unmerged}")
        print(f"  * Total normalized rows: {total_rows_normalized}")
        print(f"  * Normalization runtime: {norm_time_total:.3f}s (Avg {norm_time_total / len(files):.3f}s / file)")
        print(f"  * Queries: {len(queries)} | Ground Truth Answers: {len(gt_map)}")
        print(f"  * Language Distribution: {lang_dist}")

    return summary_stats


if __name__ == "__main__":
    stats = run_comprehensive_audit()

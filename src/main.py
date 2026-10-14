"""Entrypoint for Meetly AI 2026 Bang C Solution."""

import argparse
import json
import os
import sys
from pathlib import Path
import pandas as pd

from src.normalizer import load_normalized_workbook
from src.sanitizer import sanitize_answer
from src.solver import query_qwen, execute_code_safely


def main():
    parser = argparse.ArgumentParser(description="Meetly AI 2026 TableQA Runner")
    parser.add_argument("--xlsx_dir", type=str, default="data/data_public_1/xlsx_files", help="Path to directory containing .xlsx files")
    parser.add_argument("--queries", type=str, default="data/data_public_1/queries.json", help="Path to queries.json")
    parser.add_argument("--output", type=str, default="submission.csv", help="Path to output submission.csv")
    args = parser.parse_args()

    xlsx_dir = Path(args.xlsx_dir)
    queries_path = Path(args.queries)
    output_path = Path(args.output)

    if not queries_path.exists():
        print(f"Error: queries file not found at {queries_path}", file=sys.stderr)
        sys.exit(1)

    with open(queries_path, "r", encoding="utf-8") as f:
        queries = json.load(f)

    results = []
    print(f"Loaded {len(queries)} queries. Processing...")

    for item in queries:
        q_id = item["id"]
        file_name = item["file_name"]
        query_text = item["query"]
        excel_path = xlsx_dir / file_name

        print(f"Processing query {q_id} on {file_name}...")
        try:
            dfs = load_normalized_workbook(excel_path)
            # Create schema summary for prompt
            schema_summary = []
            for sname, df in dfs.items():
                head_str = df.head(5).to_string()
                schema_summary.append(f"Sheet: '{sname}' (Shape: {df.shape})\nFirst 5 rows:\n{head_str}")

            prompt = f"""File: {file_name}
Sheets data overview:
{chr(10).join(schema_summary)}

User Question: {query_text}

Write a python function `def solve(dfs: dict[str, pd.DataFrame]) -> Any:` to compute and return the answer.
"""
            code = query_qwen(prompt)
            raw_ans, err = execute_code_safely(code, dfs)
            if err:
                print(f"Execution warning for {q_id}: {err}")
                final_ans = ""
            else:
                final_ans = sanitize_answer(raw_ans, query_text)
        except Exception as e:
            print(f"Error processing {q_id}: {e}")
            final_ans = ""

        results.append({"id": q_id, "answer": final_ans})

    out_df = pd.DataFrame(results)
    out_df.to_csv(output_path, index=False)
    print(f"Generated results saved to {output_path}")


if __name__ == "__main__":
    main()

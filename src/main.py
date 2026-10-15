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
    parser.add_argument("--model", type=str, default=None, help="LLM model ID")
    parser.add_argument("--provider", type=str, default=None, choices=["openrouter", "groq"], help="LLM Provider (groq or openrouter)")
    parser.add_argument("--output", type=str, default="submission.csv", help="Path to output submission.csv")
    parser.add_argument("--eval", action="store_true", help="Compare output against ground truth in sample_submission.csv")
    args = parser.parse_args()

    xlsx_dir = Path(args.xlsx_dir)
    queries_path = Path(args.queries)
    output_path = Path(args.output)

    if not queries_path.exists():
        print(f"Error: queries file not found at {queries_path}", file=sys.stderr)
        sys.exit(1)

    with open(queries_path, "r", encoding="utf-8") as f:
        queries = json.load(f)

    # Load ground truth if evaluating
    gt_map = {}
    if args.eval:
        gt_path = queries_path.parent / "sample_submission.csv"
        if gt_path.exists():
            gt_df = pd.read_csv(gt_path)
            gt_map = dict(zip(gt_df["id"].astype(str), gt_df["answer"].astype(str)))

    results = []
    print(f"Loaded {len(queries)} queries. Processing with model: {args.model or 'default'}...")

    correct_count = 0
    for item in queries:
        q_id = str(item["id"])
        file_name = item["file_name"]
        query_text = item["query"]
        excel_path = xlsx_dir / file_name

        print(f"\n--- [{q_id}] ({file_name}) ---")
        print(f"Q: {query_text}")
        try:
            dfs = load_normalized_workbook(excel_path)
            # Create compact, high-information schema summary
            schema_summary = []
            for sname, df in dfs.items():
                info = [f"Sheet '{sname}' ({df.shape[0]} rows, {df.shape[1]} cols):"]
                info.append(f"Columns: {list(df.columns)}")
                # Unique row labels from col 0 to help model match exact strings
                u_labels = [str(x) for x in df.iloc[:, 0].dropna().unique() if str(x) != 'nan'][:25]
                info.append(f"Row categories (col 0): {u_labels}")
                schema_summary.append("\n".join(info))

            prompt = f"""File: {file_name}
Sheets data overview:
{chr(10).join(schema_summary)}

User Question: {query_text}

Write a python function `def solve(dfs: dict[str, pd.DataFrame]) -> Any:` to compute and return the answer.
"""
            kwargs = {}
            if args.model:
                kwargs["model"] = args.model
            if args.provider:
                kwargs["provider"] = args.provider
            code = query_qwen(prompt, **kwargs)
            raw_ans, err = execute_code_safely(code, dfs)

            # Self-Correction Reflection Loop
            retries = 0
            while err and retries < 2:
                retries += 1
                last_err_line = err.strip().splitlines()[-1] if err.strip() else err
                print(f"Execution error (attempt {retries}): {last_err_line}")
                print(f"Triggering Self-Correction Reflection (attempt {retries})...")
                short_err = "\n".join(err.strip().splitlines()[-4:])
                reflection_prompt = f"""File: {file_name}
Sheets data overview:
{chr(10).join(schema_summary)}

User Question: {query_text}

Your previous code produced this error:
{short_err}

Please fix the error and write a correct python function `def solve(dfs: dict[str, pd.DataFrame]) -> Any:`
"""
                code = query_qwen(reflection_prompt, **kwargs)
                raw_ans, err = execute_code_safely(code, dfs)

            if err:
                print(f"Final Execution warning: {err}")
                final_ans = ""
            else:
                final_ans = sanitize_answer(raw_ans, query_text)
        except Exception as e:
            print(f"Error: {e}")
            final_ans = ""

        print(f"-> Prediction: '{final_ans}'")
        if q_id in gt_map:
            target = gt_map[q_id]
            is_match = (str(final_ans).strip() == str(target).strip())
            print(f"-> Ground Truth: '{target}' | Match: {'✅ YES' if is_match else '❌ NO'}")
            if is_match:
                correct_count += 1

        results.append({"id": q_id, "answer": final_ans})
        import time
        time.sleep(1.0)

    out_df = pd.DataFrame(results)
    out_df.to_csv(output_path, index=False)
    print(f"\n==========================================")
    print(f"Generated results saved to {output_path}")
    if gt_map:
        total = len(gt_map)
        acc = (correct_count / total) * 100
        print(f"Exact Match Score: {correct_count}/{total} ({acc:.1f}%)")
    print(f"==========================================")


if __name__ == "__main__":
    main()

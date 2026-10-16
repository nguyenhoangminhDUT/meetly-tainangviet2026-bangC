"""Entrypoint for Meetly AI 2026 Bang C Spreadsheet QA Solution."""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional
import pandas as pd

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from src.normalizer import load_normalized_workbook
    from src.sanitizer import sanitize_answer
    from src.schema_builder import build_schema_summary
    from src.solver import query_llm, execute_code_safely, TOKEN_STATS
except ImportError:
    from normalizer import load_normalized_workbook
    from sanitizer import sanitize_answer
    from schema_builder import build_schema_summary
    from solver import query_llm, execute_code_safely, TOKEN_STATS


class TeeLogger:
    """Simultaneously writes console output to terminal and a detailed log file."""
    def __init__(self, filename: str):
        self.terminal = sys.stdout
        self.log = open(filename, "w", encoding="utf-8")

    def write(self, message: str):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()


def load_ground_truth(queries_path: Path, answers_arg: Optional[str] = None) -> Dict[str, str]:
    """Loads ground truth answers from answers.json or sample_submission.csv if available."""
    gt_map: Dict[str, str] = {}
    candidates = []
    if answers_arg:
        candidates.append(Path(answers_arg))
    candidates.append(queries_path.parent / "answers.json")
    candidates.append(queries_path.parent / "sample_submission.csv")

    for path in candidates:
        if path.exists():
            if path.suffix.lower() == ".json":
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for item in data:
                        gt_map[str(item.get("id"))] = str(item.get("answer", "")).strip()
                    print(f"[*] Loaded {len(gt_map)} ground truth answers from JSON: {path}")
                    break
                except Exception as e:
                    print(f"[!] Warning reading {path}: {e}")
            elif path.suffix.lower() == ".csv":
                try:
                    df = pd.read_csv(path)
                    ans_col = "answer" if "answer" in df.columns else df.columns[1]
                    id_col = "id" if "id" in df.columns else df.columns[0]
                    for _, row in df.iterrows():
                        gt_map[str(row[id_col])] = str(row[ans_col]).strip()
                    print(f"[*] Loaded {len(gt_map)} ground truth answers from CSV: {path}")
                    break
                except Exception as e:
                    print(f"[!] Warning reading {path}: {e}")

    return gt_map


def main():
    parser = argparse.ArgumentParser(description="Meetly AI 2026 Spreadsheet QA Runner")
    parser.add_argument("--xlsx_dir", type=str, default="data/data_public_1/xlsx_files", help="Path to directory containing .xlsx files")
    parser.add_argument("--queries", type=str, default="data/data_public_1/queries.json", help="Path to queries.json")
    parser.add_argument("--answers", type=str, default=None, help="Path to ground truth answers.json or sample_submission.csv for evaluation")
    parser.add_argument("--model", type=str, default=None, help="LLM model ID (e.g. llama-3.1-8b-instant, gemma2-9b-it, gemini-1.5-flash, qwen/qwen3.7-flash)")
    parser.add_argument("--provider", type=str, default=None, choices=["openrouter", "groq", "gemini", "ollama"], help="LLM Provider (openrouter, groq, gemini, or ollama)")
    parser.add_argument("--output", type=str, default="submission.csv", help="Path to output submission.csv")
    parser.add_argument("--log_file", type=str, default="eval_detail_log.txt", help="Path to save detailed execution log")
    parser.add_argument("--eval", action="store_true", help="Compare output against ground truth answers")
    args = parser.parse_args()

    if args.log_file:
        sys.stdout = TeeLogger(args.log_file)

    xlsx_dir = Path(args.xlsx_dir)
    queries_path = Path(args.queries)
    output_path = Path(args.output)

    if not queries_path.exists():
        print(f"Error: queries file not found at {queries_path}", file=sys.stderr)
        sys.exit(1)

    with open(queries_path, "r", encoding="utf-8") as f:
        queries = json.load(f)

    # Load ground truth if evaluation is requested
    gt_map = load_ground_truth(queries_path, args.answers) if args.eval else {}

    results = []
    print(f"Loaded {len(queries)} queries. Processing with model: {args.model or 'default'}...")

    correct_count = 0
    total_eval = 0

    for idx, item in enumerate(queries, start=1):
        q_id = str(item["id"])
        file_name = item["file_name"]
        query_text = item["query"]
        excel_path = xlsx_dir / file_name

        print(f"\n--- [{idx}/{len(queries)}] Query ID {q_id} ({file_name}) ---")
        print(f"Q: {query_text}")

        try:
            dfs = load_normalized_workbook(excel_path)
            schema_summary = build_schema_summary(dfs, query_text)

            prompt = f"""File: {file_name}
Sheets data overview:
{schema_summary}

User Question: {query_text}

Write a python function `def solve(dfs: dict[str, pd.DataFrame]) -> Any:` to compute and return the answer.
"""
            kwargs = {}
            if args.model:
                kwargs["model"] = args.model
            if args.provider:
                kwargs["provider"] = args.provider

            code = query_llm(prompt, **kwargs)
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
{schema_summary}

User Question: {query_text}

Your previous code produced this error:
{short_err}

Please fix the error and write a correct python function `def solve(dfs: dict[str, pd.DataFrame]) -> Any:`
"""
                code = query_llm(reflection_prompt, **kwargs)
                raw_ans, err = execute_code_safely(code, dfs)

            if err:
                print(f"Final Execution warning: {err}")
                final_ans = ""
            else:
                final_ans = sanitize_answer(raw_ans, query_text)

        except Exception as e:
            print(f"Error during processing: {e}")
            final_ans = ""

        print(f"-> Prediction: '{final_ans}'")
        print(f"-> Tokens for query: {TOKEN_STATS['last_total_tokens']} (Prompt: {TOKEN_STATS['last_prompt_tokens']}, Output: {TOKEN_STATS['last_completion_tokens']})")

        if q_id in gt_map:
            total_eval += 1
            target = gt_map[q_id]
            is_match = (str(final_ans).strip() == str(target).strip())
            print(f"-> Ground Truth: '{target}' | Match: {'✅ YES' if is_match else '❌ NO'}")
            if is_match:
                correct_count += 1

        results.append({"id": q_id, "answer": final_ans})
        time.sleep(0.5)

    out_df = pd.DataFrame(results)
    out_df.to_csv(output_path, index=False)
    print(f"\n==========================================")
    print(f"Generated results saved to {output_path}")
    if total_eval > 0:
        acc = (correct_count / total_eval) * 100
        print(f"Exact Match Score: {correct_count}/{total_eval} ({acc:.1f}%)")
    print(f"------------------------------------------")
    print(f"LLM Token Usage Summary:")
    print(f"  • Total API Calls: {TOKEN_STATS['call_count']}")
    print(f"  • Total Prompt Tokens: {TOKEN_STATS['prompt_tokens']:,}")
    print(f"  • Total Output Tokens: {TOKEN_STATS['completion_tokens']:,}")
    print(f"  • Total Tokens Used: {TOKEN_STATS['total_tokens']:,}")
    avg_tok = TOKEN_STATS['total_tokens'] / max(1, len(queries))
    print(f"  • Average Tokens per Query: {avg_tok:.1f}")
    est_cost = (TOKEN_STATS['prompt_tokens'] * 0.03 + TOKEN_STATS['completion_tokens'] * 0.13) / 1_000_000
    print(f"  • Est. Cost (qwen/qwen3.7-flash): ${est_cost:.6f} USD")
    print(f"  • Avg Cost per Query: ${est_cost / max(1, len(queries)):.6f} USD")
    print(f"==========================================")


if __name__ == "__main__":
    main()

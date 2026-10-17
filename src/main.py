"""Main Entrypoint for Meetly Table QA Solution.

Competition Execution Standard (Tài Năng Việt 2026 - Bảng C):
- CLI Signature:
    python -m src.main --xlsx_dir <path_to_xlsx> --queries <path_to_queries.json> --output submission.csv
- Model: Qwen3.7 Flash (`qwen/qwen3.7-flash`) via OpenRouter API
- Authentication: OPENROUTER_API_KEY environment variable or --api_key argument
- Output: Standard submission.csv with exactly two columns: `id,answer`
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from src.normalizer import load_normalized_workbook
    from src.sanitizer import sanitize_answer
    from src.schema_builder import build_schema_summary
    from src.solver import query_llm, execute_code_safely
    from src.llm_client import COMPETITION_MODEL_ID, TOKEN_STATS, get_token_usage_report
except ImportError:
    from normalizer import load_normalized_workbook
    from sanitizer import sanitize_answer
    from schema_builder import build_schema_summary
    from solver import query_llm, execute_code_safely
    from llm_client import COMPETITION_MODEL_ID, TOKEN_STATS, get_token_usage_report


class OutputLogger:
    """Mirrors console output to both terminal and log file if specified."""
    def __init__(self, filename: Optional[str] = None):
        self.terminal = sys.stdout
        self.log = open(filename, "w", encoding="utf-8") if filename else None

    def write(self, message: str):
        self.terminal.write(message)
        if self.log:
            self.log.write(message)
            self.log.flush()

    def flush(self):
        self.terminal.flush()
        if self.log:
            self.log.flush()


def load_ground_truth(queries_path: Path, answers_arg: Optional[str] = None) -> Dict[str, str]:
    """Loads ground truth answers if available for local benchmarking."""
    gt_map: Dict[str, str] = {}
    candidates: List[Path] = []
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
                    break
                except Exception:
                    pass
            elif path.suffix.lower() == ".csv":
                try:
                    df = pd.read_csv(path)
                    ans_col = "answer" if "answer" in df.columns else df.columns[1]
                    id_col = "id" if "id" in df.columns else df.columns[0]
                    for _, row in df.iterrows():
                        gt_map[str(row[id_col])] = str(row[ans_col]).strip()
                    break
                except Exception:
                    pass
    return gt_map


def main():
    parser = argparse.ArgumentParser(
        description="Meetly Spreadsheet QA Runner (Tài Năng Việt 2026 - Bảng C)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Competition required parameters
    parser.add_argument("--xlsx_dir", type=str, required=True, help="Directory containing input .xlsx spreadsheet files")
    parser.add_argument("--queries", type=str, required=True, help="Path to input queries.json file")
    parser.add_argument("--output", type=str, default="submission.csv", help="Path to write output submission.csv")

    # Model and connection settings
    parser.add_argument("--api_key", type=str, default=None, help="API key for selected provider")
    parser.add_argument("--model", type=str, default=None, help="LLM model identifier (defaults to provider's native model)")
    parser.add_argument("--provider", type=str, default="openrouter", choices=["openrouter", "groq", "gemini", "ollama", "selfhosted"], help="LLM provider")

    # Evaluation and logging utilities
    parser.add_argument("--eval", action="store_true", help="Evaluate against ground truth answers if present in data directory")
    parser.add_argument("--answers", type=str, default=None, help="Path to explicit answers file for evaluation")
    parser.add_argument("--log_file", type=str, default=None, help="Optional log file path")
    args = parser.parse_args()

    if args.log_file:
        sys.stdout = OutputLogger(args.log_file)

    xlsx_dir = Path(args.xlsx_dir)
    queries_path = Path(args.queries)
    output_path = Path(args.output)

    if not xlsx_dir.exists():
        print(f"Error: xlsx_dir directory does not exist: {xlsx_dir}", file=sys.stderr)
        sys.exit(1)
    if not queries_path.exists():
        print(f"Error: queries file does not exist: {queries_path}", file=sys.stderr)
        sys.exit(1)

    with open(queries_path, "r", encoding="utf-8") as f:
        queries = json.load(f)

    gt_map = load_ground_truth(queries_path, args.answers) if args.eval else {}

    print("=" * 80)
    print("MEETLY SPREADSHEET QUESTION ANSWERING PIPELINE")
    print("=" * 80)
    print(f"  • Workbooks Directory : {xlsx_dir}")
    print(f"  • Queries File        : {queries_path} ({len(queries)} queries)")
    print(f"  • Target Output       : {output_path}")
    print(f"  • LLM Provider        : {args.provider}")
    print(f"  • LLM Model           : {args.model}")
    print("=" * 80)

    results: List[Dict[str, str]] = []
    correct_count = 0
    total_eval = 0

    # Cache loaded workbooks to avoid redundant disk I/O when multiple queries share a workbook
    workbook_cache: Dict[str, Dict[str, pd.DataFrame]] = {}

    start_total_time = time.time()

    for idx, item in enumerate(queries, start=1):
        q_id = str(item["id"])
        file_name = item.get("file_name") or item.get("xlsx_file", "")
        query_text = str(item.get("query", "")).strip()
        excel_path = xlsx_dir / file_name

        print(f"\n[{idx:02d}/{len(queries):02d}] Processing Query ID: {q_id} | Workbook: {file_name}")
        print(f"     Q: \"{query_text}\"")

        q_t0 = time.time()
        final_ans = ""

        try:
            # 1. Load & Normalize Spreadsheet (Cached)
            if file_name not in workbook_cache:
                if not excel_path.exists():
                    raise FileNotFoundError(f"Spreadsheet file not found: {excel_path}")
                workbook_cache[file_name] = load_normalized_workbook(excel_path)
            dfs = workbook_cache[file_name]

            # 2. Extract Token-Optimized Schema Summary
            schema_summary = build_schema_summary(dfs, query_text)

            # 3. Construct PoT Reasoning Prompt
            prompt = f"""File: {file_name}
Sheets data overview:
{schema_summary}

User Question: {query_text}

Write a python function `def solve(dfs: dict[str, pd.DataFrame]) -> Any:` to compute and return the answer.
"""
            # 4. Invoke LLM for Python Code Generation
            kwargs: Dict[str, Any] = {
                "api_key": args.api_key,
                "model": args.model,
                "provider": args.provider,
            }

            code = query_llm(prompt, **kwargs)
            raw_ans, err = execute_code_safely(code, dfs)

            # 5. Self-Correction Reflection Loop on Execution Exceptions (Max 2 retries)
            retries = 0
            while err and retries < 2:
                retries += 1
                short_err = "\n".join(err.strip().splitlines()[-4:])
                print(f"     [!] Sandbox execution error (retry {retries}/2): {short_err}")
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

            # 6. Apply Exact Match Post-Processing Sanitizer
            if err:
                print(f"     [!] Unresolved execution error: {err.strip().splitlines()[-1]}")
                final_ans = ""
            else:
                final_ans = sanitize_answer(raw_ans, query_text)

        except Exception as e:
            print(f"     [!] Processing exception for Query {q_id}: {e}")
            final_ans = ""

        elapsed = time.time() - q_t0
        print(f"     -> Answer : '{final_ans}' ({elapsed:.2f}s)")

        # Optional live evaluation if ground truth is present
        if q_id in gt_map:
            total_eval += 1
            target = gt_map[q_id]
            is_match = (str(final_ans).strip() == str(target).strip())
            status = "✅ PASS" if is_match else "❌ FAIL"
            print(f"     -> Target : '{target}' | Status: {status}")
            if is_match:
                correct_count += 1

        results.append({"id": q_id, "answer": final_ans})
        time.sleep(1.0)

    # Save output submission.csv
    output_df = pd.DataFrame(results)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_path, index=False, encoding="utf-8")

    total_time = time.time() - start_total_time
    token_report = get_token_usage_report(len(queries))

    print("\n" + "=" * 80)
    print("PIPELINE EXECUTION SUMMARY")
    print("=" * 80)
    print(f"  • Submission Output File : {output_path.resolve()}")
    print(f"  • Total Queries Processed: {len(results)}")
    print(f"  • Total Elapsed Time     : {total_time:.2f}s (Avg {total_time/max(1, len(results)):.2f}s / query)")
    if total_eval > 0:
        acc = (correct_count / total_eval) * 100.0
        print(f"  • Exact Match Score      : {correct_count}/{total_eval} ({acc:.1f}%)")
    print("-" * 80)
    print("LLM RESOURCE & TOKEN ACCOUNTING:")
    print(f"  • Total API Invocations  : {token_report['call_count']}")
    print(f"  • Total Prompt Tokens    : {token_report['prompt_tokens']:,}")
    print(f"  • Total Output Tokens    : {token_report['completion_tokens']:,}")
    print(f"  • Total Tokens Used      : {token_report['total_tokens']:,}")
    print(f"  • Avg Tokens per Query   : {token_report['avg_tokens_per_query']}")
    print(f"  • Estimated Cost (USD)   : ${token_report['estimated_cost_usd']:.6f}")
    print(f"  • Avg Cost per Query     : ${token_report['avg_cost_per_query_usd']:.6f} (Limit: $0.10/query)")
    print("=" * 80)


if __name__ == "__main__":
    main()

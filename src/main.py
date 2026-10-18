"""Main Entrypoint for Meetly Table QA Solution.

Competition Execution Standard (Tài Năng Việt 2026 - Bảng C):
- CLI Signature:
    python -m src.main --xlsx_dir <path_to_xlsx> --queries <path_to_queries.json> --output submission.csv
- Model: Qwen3.7 Flash (`qwen/qwen3.7-flash`) via OpenRouter API
- Authentication: OPENROUTER_API_KEY environment variable or --api_key argument
- Performance: Pre-warmed workbook cache, concurrent thread execution (--workers 4)
- Output: Standard submission.csv with exactly two columns: `id,answer`
"""

import argparse
import concurrent.futures
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from src.normalizer import load_normalized_workbook
    from src.sanitizer import sanitize_answer
    from src.schema_builder import build_schema_summary
    from src.solver import query_llm, execute_code_safely, is_empty_or_meaningless, get_column_samples_hint
    from src.llm_client import COMPETITION_MODEL_ID, TOKEN_STATS, get_token_usage_report
    from src.evaluator import compute_metrics_from_maps
except ModuleNotFoundError as e:
    if e.name in ("src", "src.normalizer", "src.sanitizer", "src.schema_builder", "src.solver", "src.llm_client", "src.evaluator"):
        from normalizer import load_normalized_workbook
        from sanitizer import sanitize_answer
        from schema_builder import build_schema_summary
        from solver import query_llm, execute_code_safely, is_empty_or_meaningless, get_column_samples_hint
        from llm_client import COMPETITION_MODEL_ID, TOKEN_STATS, get_token_usage_report
        from evaluator import compute_metrics_from_maps
    else:
        raise


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
    candidates.extend([
        queries_path.parent / "answers.json",
        queries_path.parent / "sample_submission.csv",
        queries_path.parent / "sample_answers.csv",
    ])

    for p in candidates:
        if p.exists():
            if p.suffix.lower() == ".json":
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for item in data:
                        if "id" in item and "answer" in item:
                            gt_map[str(item["id"])] = str(item["answer"]).strip()
                    break
                except Exception:
                    pass
            elif p.suffix.lower() == ".csv":
                try:
                    df = pd.read_csv(p)
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
        description="Meetly Spreadsheet QA Runner (Tài Năng Việt 2026 - Bảng C - Đội AI26C0079)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Competition required parameters with aliases
    parser.add_argument("--xlsx_dir", "--input_dir", "--data_dir", dest="xlsx_dir", type=str, default=None, help="Directory containing input .xlsx spreadsheet files")
    parser.add_argument("--queries", "--queries_path", "--query_file", dest="queries", type=str, default=None, help="Path to input queries.json file")
    parser.add_argument("--output", "--output_path", "--out", dest="output", type=str, default=None, help="Path to write output submission.csv (default: submission.csv)")

    # Model and connection settings
    parser.add_argument("--api_key", type=str, default=None, help="API key for selected provider")
    parser.add_argument("--model", type=str, default=None, help="LLM model identifier (defaults to provider's native model)")
    parser.add_argument("--provider", type=str, default="openrouter", choices=["openrouter", "groq", "gemini", "ollama", "selfhosted"], help="LLM provider")

    # High-Performance Concurrency
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent worker threads for parallel question answering")

    # Evaluation and logging utilities
    parser.add_argument("--eval", action="store_true", help="Evaluate against ground truth answers if present in data directory")
    parser.add_argument("--answers", type=str, default=None, help="Path to explicit answers file for evaluation")
    parser.add_argument("--log_file", type=str, default=None, help="Optional log file path")

    # Optional Positional Arguments Fallback (for docker entrypoint without flags)
    parser.add_argument("pos_xlsx_dir", nargs="?", default=None, help="Positional fallback for xlsx directory")
    parser.add_argument("pos_queries", nargs="?", default=None, help="Positional fallback for queries file")
    parser.add_argument("pos_output", nargs="?", default=None, help="Positional fallback for output file")

    args = parser.parse_args()

    actual_xlsx_dir = args.xlsx_dir or args.pos_xlsx_dir
    actual_queries = args.queries or args.pos_queries
    actual_output = args.output or args.pos_output or "submission.csv"

    if not actual_xlsx_dir or not actual_queries:
        parser.error("Both xlsx_dir (via --xlsx_dir / --input_dir / positional) and queries (via --queries / positional) are required.")

    if args.log_file:
        sys.stdout = OutputLogger(args.log_file)

    xlsx_dir = Path(actual_xlsx_dir)
    queries_path = Path(actual_queries)
    output_path = Path(actual_output)

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
    print(f"  • Concurrent Workers  : {args.workers}")
    print("=" * 80)

    # 1. Pre-warm Workbook Cache to separate Disk I/O from network queries and prevent thread contention
    unique_files = list(dict.fromkeys(
        q.get("file_name") or q.get("xlsx_file", "")
        for q in queries
        if (q.get("file_name") or q.get("xlsx_file"))
    ))
    print(f"[*] Pre-warming Workbook Cache ({len(unique_files)} unique workbooks)...")
    t_warm = time.time()
    workbook_cache: Dict[str, Dict[str, pd.DataFrame]] = {}
    for fname in unique_files:
        excel_path = xlsx_dir / fname
        if excel_path.exists():
            workbook_cache[fname] = load_normalized_workbook(excel_path)
        else:
            print(f"    [!] Warning: Spreadsheet file not found: {excel_path}")
    print(f"    -> Normalized & cached {len(workbook_cache)} workbooks in {time.time() - t_warm:.2f}s\n")

    print_lock = threading.Lock()

    def process_query_item(item_tuple: Tuple[int, Dict[str, Any]]) -> Dict[str, Any]:
        idx, item = item_tuple
        q_id = str(item["id"])
        file_name = item.get("file_name") or item.get("xlsx_file", "")
        query_text = str(item.get("query", "")).strip()

        q_t0 = time.time()
        final_ans = ""
        log_lines = [
            f"[{idx:02d}/{len(queries):02d}] Processing Query ID: {q_id} | Workbook: {file_name}",
            f"     Q: \"{query_text}\"",
        ]

        try:
            # Retrieve normalized sheets from pre-warmed cache (or load on demand)
            dfs = workbook_cache.get(file_name)
            if dfs is None:
                excel_path = xlsx_dir / file_name
                if not excel_path.exists():
                    raise FileNotFoundError(f"Spreadsheet file not found: {excel_path}")
                dfs = load_normalized_workbook(excel_path)

            # Extract Token-Optimized Schema Summary
            schema_summary = build_schema_summary(dfs, query_text)

            # Construct PoT Reasoning Prompt
            prompt = f"""File: {file_name}
Sheets data overview:
{schema_summary}

User Question: {query_text}

Write a python function `def solve(dfs: dict[str, pd.DataFrame]) -> Any:` to answer this question.
"""

            # Invoke LLM for Python Code Generation
            kwargs: Dict[str, Any] = {
                "api_key": args.api_key,
                "model": args.model,
                "provider": args.provider,
                "temperature": 0.0,
                "max_tokens": 800,
            }

            code = query_llm(prompt, **kwargs)
            raw_ans, err = execute_code_safely(code, dfs)

            # Self-Correction Reflection Loop on Execution Exceptions OR Empty/NaN Results (Max 2 retries)
            retries = 0
            while retries < 2:
                if err:
                    short_err = "\n".join(err.strip().splitlines()[-4:])
                    fail_desc = f"Sandbox execution error:\n{short_err}"
                    trigger_label = f"Exception: {short_err.splitlines()[-1]}"
                elif is_empty_or_meaningless(raw_ans):
                    sample_hints = get_column_samples_hint(dfs)
                    fail_desc = (
                        f"Function returned empty/NaN/invalid result ({raw_ans!r}).\n"
                        f"Possible Causes & Fixes:\n"
                        f"1. A DataFrame filtering condition (e.g. .str.contains or ==) matched 0 rows due to case/spacing. "
                        f"Use flexible matching: `.str.contains(..., case=False, na=False)` or `.str.strip().str.lower()`.\n"
                        f"2. A numeric calculation failed or produced NaN because strings contain symbols ('$', '%', ','). "
                        f"Strip symbols before converting to numeric: `.str.replace(r'[$%,]', '', regex=True)`.\n\n"
                        f"Sample column values for reference:\n{sample_hints}"
                    )
                    trigger_label = f"Empty/NaN result ({raw_ans!r})"
                else:
                    # Valid non-empty answer produced
                    break

                retries += 1
                log_lines.append(f"     [!] Reflection trigger ({retries}/2): {trigger_label}")
                reflection_prompt = f"""File: {file_name}
Sheets data overview:
{schema_summary}

User Question: {query_text}

Your previous code produced this issue:
{fail_desc}

Please fix the error or filtering condition and write a correct python function `def solve(dfs: dict[str, pd.DataFrame]) -> Any:`
"""
                code = query_llm(reflection_prompt, **kwargs)
                raw_ans, err = execute_code_safely(code, dfs)

            # Apply Exact Match Post-Processing Sanitizer
            if err:
                log_lines.append(f"     [!] Unresolved execution error: {err.strip().splitlines()[-1]}")
                final_ans = ""
            elif is_empty_or_meaningless(raw_ans):
                log_lines.append(f"     [!] Unresolved empty/NaN result: {raw_ans!r}")
                final_ans = ""
            else:
                final_ans = sanitize_answer(raw_ans, query_text)

        except Exception as e:
            log_lines.append(f"     [!] Processing exception for Query {q_id}: {e}")
            final_ans = ""

        elapsed = time.time() - q_t0
        log_lines.append(f"     -> Answer : '{final_ans}' ({elapsed:.2f}s)")

        if q_id in gt_map:
            target = gt_map[q_id]
            is_match = (str(final_ans).strip() == str(target).strip())
            status = "✅ PASS" if is_match else "❌ FAIL"
            log_lines.append(f"     -> Target : '{target}' | Status: {status}")

        with print_lock:
            print("\n" + "\n".join(log_lines))

        return {
            "index": idx,
            "id": q_id,
            "answer": final_ans,
            "elapsed": elapsed,
        }

    start_total_time = time.time()
    raw_results: List[Dict[str, Any]] = []

    # Parallel Execution with ThreadPoolExecutor
    if args.workers > 1 and len(queries) > 1:
        print(f"[*] Dispatching {len(queries)} queries across {args.workers} concurrent worker threads...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_idx = {
                executor.submit(process_query_item, (idx, item)): idx
                for idx, item in enumerate(queries, start=1)
            }
            for future in concurrent.futures.as_completed(future_to_idx):
                raw_results.append(future.result())
    else:
        for idx, item in enumerate(queries, start=1):
            raw_results.append(process_query_item((idx, item)))

    # Guarantee 100% original order preservation matching queries.json
    raw_results.sort(key=lambda r: r["index"])
    results = [{"id": r["id"], "answer": r["answer"]} for r in raw_results]

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

    if gt_map:
        pred_map = {r["id"]: r["answer"] for r in results}
        eval_metrics = compute_metrics_from_maps(pred_map, gt_map)
        print("-" * 80)
        print("DIAGNOSTIC BENCHMARK EVALUATION:")
        print(f"  • Strict Exact Match (EM) : {eval_metrics['strict_correct']}/{eval_metrics['total']} ({eval_metrics['strict_accuracy']:.1f}%)")
        print(f"  • Normalized Match (Norm) : {eval_metrics['norm_correct']}/{eval_metrics['total']} ({eval_metrics['norm_accuracy']:.1f}%)")
        print(f"  • Avg Edit Similarity     : {eval_metrics['avg_edit_similarity']:.2f}%")
        print(f"  • Avg Character Error Rate: {eval_metrics['avg_cer']:.4f}")
        print(f"  • Avg Rel Numeric Error   : {eval_metrics['avg_rne']:.6f} ({eval_metrics['numeric_queries_count']} numeric queries)")

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

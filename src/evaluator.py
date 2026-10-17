"""Evaluation Engine: Compares submission predictions against Ground Truth with error analysis and markdown reporting.

Provides Multi-Dimensional Benchmarking Metrics:
1. Strict Exact Match (EM): Binary exact string match (Competition Primary Metric).
2. Normalized Exact Match (Norm-EM): Case-insensitive, whitespace & punctuation stripped, numeric normalized.
3. Character Error Rate (CER) & Edit Similarity: Levenshtein character-level edit distance.
4. Relative Numerical Error (RNE): Relative deviation |pred - gt| / max(|gt|, 1e-6) for numerical answers.
"""

import argparse
import json
import re
import string
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd


def compute_levenshtein(s1: str, s2: str) -> int:
    """Computes Levenshtein edit distance between two strings without third-party dependencies."""
    if len(s1) < len(s2):
        return compute_levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def normalize_for_eval(text: str) -> str:
    """Normalizes string for lenient evaluation (lowercase, punctuation, whitespace, numeric float)."""
    t = str(text).strip().lower()
    # Check numeric normalization (e.g. 11.0 -> 11, 4.70 -> 4.7)
    try:
        t_clean = re.sub(r'[\$,%€£¥₫]', '', t).replace(',', '').strip()
        val = float(t_clean)
        return str(int(val)) if val.is_integer() else f"{val:.4f}".rstrip('0').rstrip('.')
    except Exception:
        pass
    # Remove punctuation
    t = re.sub(r'[^\w\s]', '', t)
    return " ".join(t.split())


def compute_relative_numeric_error(pred_str: str, gt_str: str) -> Optional[float]:
    """Computes relative numeric error |pred - gt| / max(|gt|, 1e-6) if both are numeric."""
    try:
        p_clean = re.sub(r'[\$,%€£¥₫]', '', str(pred_str)).replace(',', '').strip()
        g_clean = re.sub(r'[\$,%€£¥₫]', '', str(gt_str)).replace(',', '').strip()
        p_val = float(p_clean)
        g_val = float(g_clean)
        denom = abs(g_val) if abs(g_val) > 1e-6 else 1.0
        return abs(p_val - g_val) / denom
    except Exception:
        return None


def evaluate_predictions(pred_path: str | Path, gt_path: str | Path) -> Dict[str, Any]:
    """Evaluates submission predictions against ground truth answers with comprehensive diagnostics."""
    pred_path = Path(pred_path)
    gt_path = Path(gt_path)

    if not pred_path.exists():
        raise FileNotFoundError(f"Predictions file not found: {pred_path}")
    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {gt_path}")

    # Load predictions
    pred_df = pd.read_csv(pred_path)
    p_id_col = "id" if "id" in pred_df.columns else pred_df.columns[0]
    p_ans_col = "answer" if "answer" in pred_df.columns else pred_df.columns[1]
    pred_map = {str(row[p_id_col]): str(row[p_ans_col]).strip() for _, row in pred_df.iterrows()}

    # Load ground truth
    gt_map: Dict[str, str] = {}
    if gt_path.suffix.lower() == ".json":
        with open(gt_path, "r", encoding="utf-8") as f:
            gt_data = json.load(f)
        for item in gt_data:
            gt_map[str(item.get("id"))] = str(item.get("answer", "")).strip()
    else:
        gt_df = pd.read_csv(gt_path)
        g_id_col = "id" if "id" in gt_df.columns else gt_df.columns[0]
        g_ans_col = "answer" if "answer" in gt_df.columns else gt_df.columns[1]
        for _, row in gt_df.iterrows():
            gt_map[str(row[g_id_col])] = str(row[g_ans_col]).strip()

    return compute_metrics_from_maps(pred_map, gt_map)


def compute_metrics_from_maps(pred_map: Dict[str, str], gt_map: Dict[str, str]) -> Dict[str, Any]:
    """Computes exact match and diagnostic metrics from in-memory prediction and ground truth maps."""
    total = len(gt_map)
    strict_correct = 0
    norm_correct = 0
    cer_list: List[float] = []
    sim_list: List[float] = []
    rne_list: List[float] = []
    detailed_results = []

    for q_id, target in gt_map.items():
        pred = pred_map.get(q_id, "")
        is_strict_match = (str(pred).strip() == str(target).strip())
        is_norm_match = (normalize_for_eval(pred) == normalize_for_eval(target))

        if is_strict_match:
            strict_correct += 1
        if is_norm_match:
            norm_correct += 1

        # Edit distance & similarity
        dist = compute_levenshtein(str(pred), str(target))
        denom = max(len(str(target)), 1)
        cer = dist / denom
        edit_sim = max(0.0, 1.0 - (dist / max(len(str(pred)), len(str(target)), 1)))
        cer_list.append(cer)
        sim_list.append(edit_sim)

        # Relative Numeric Error
        rne = compute_relative_numeric_error(pred, target)
        if rne is not None:
            rne_list.append(rne)

        detailed_results.append({
            "id": q_id,
            "prediction": pred,
            "ground_truth": target,
            "strict_match": is_strict_match,
            "norm_match": is_norm_match,
            "edit_similarity": edit_sim,
            "rne": rne
        })

    strict_acc = (strict_correct / total * 100.0) if total > 0 else 0.0
    norm_acc = (norm_correct / total * 100.0) if total > 0 else 0.0
    avg_cer = (sum(cer_list) / len(cer_list)) if cer_list else 0.0
    avg_sim = (sum(sim_list) / len(sim_list) * 100.0) if sim_list else 100.0
    avg_rne = (sum(rne_list) / len(rne_list)) if rne_list else 0.0

    return {
        "total": total,
        "strict_correct": strict_correct,
        "strict_accuracy": strict_acc,
        "norm_correct": norm_correct,
        "norm_accuracy": norm_acc,
        "avg_cer": avg_cer,
        "avg_edit_similarity": avg_sim,
        "numeric_queries_count": len(rne_list),
        "avg_rne": avg_rne,
        "details": detailed_results
    }


def generate_markdown_report(metrics: Dict[str, Any], title: str = "Evaluation Report") -> str:
    """Generates a clean GitHub-flavored markdown evaluation report with full diagnostics."""
    lines = [
        f"# 📊 {title}",
        "",
        "### 🎯 Summary Performance & Diagnostic Metrics",
        f"- **Total Queries Evaluated**: {metrics['total']}",
        f"- **Strict Exact Match (EM)**: **{metrics['strict_correct']} / {metrics['total']} ({metrics['strict_accuracy']:.1f}%)**",
        f"- **Normalized Exact Match (Norm-EM)**: {metrics['norm_correct']} / {metrics['total']} ({metrics['norm_accuracy']:.1f}%)",
        f"- **Average Character Edit Similarity**: {metrics['avg_edit_similarity']:.2f}%",
        f"- **Average Character Error Rate (CER)**: {metrics['avg_cer']:.4f}",
        f"- **Average Relative Numeric Error (RNE)**: {metrics['avg_rne']:.6f} ({metrics['numeric_queries_count']} numeric queries)",
        "",
        "### 🔍 Detailed Per-Query Verification",
        "| ID | Prediction | Ground Truth | Strict Match | Norm Match | Sim (%) |",
        "| :---: | :--- | :--- | :---: | :---: | :---: |"
    ]

    for item in metrics["details"]:
        s_status = "✅ PASS" if item["strict_match"] else "❌ FAIL"
        n_status = "✅" if item["norm_match"] else "❌"
        sim_str = f"{item['edit_similarity']*100:.1f}%"
        lines.append(f"| {item['id']} | `{item['prediction']}` | `{item['ground_truth']}` | {s_status} | {n_status} | {sim_str} |")

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Spreadsheet QA predictions")
    parser.add_argument("--pred", type=str, required=True, help="Path to predictions submission.csv")
    parser.add_argument("--gt", type=str, required=True, help="Path to ground truth answers.json or sample_submission.csv")
    parser.add_argument("--report", type=str, default=None, help="Optional output path for markdown report")
    args = parser.parse_args()

    results = evaluate_predictions(args.pred, args.gt)
    print("\n" + "=" * 60)
    print("COMPREHENSIVE BENCHMARK EVALUATION RESULTS")
    print("=" * 60)
    print(f"  • Strict Exact Match (EM) : {results['strict_correct']}/{results['total']} ({results['strict_accuracy']:.1f}%)")
    print(f"  • Normalized Match (Norm) : {results['norm_correct']}/{results['total']} ({results['norm_accuracy']:.1f}%)")
    print(f"  • Avg Edit Similarity     : {results['avg_edit_similarity']:.2f}%")
    print(f"  • Avg Character Error Rate: {results['avg_cer']:.4f}")
    print(f"  • Avg Rel Numeric Error   : {results['avg_rne']:.6f}")
    print("=" * 60)

    if args.report:
        md_text = generate_markdown_report(results, f"Evaluation Report: {Path(args.pred).name}")
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(md_text)
        print(f"[V] Report written to: {args.report}")

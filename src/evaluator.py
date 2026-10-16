"""Evaluation Engine: Compares submission predictions against Ground Truth with error analysis and markdown reporting."""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
import pandas as pd


def evaluate_predictions(pred_path: str | Path, gt_path: str | Path) -> Dict[str, Any]:
    """Evaluates submission predictions against ground truth answers."""
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
        gt_map = {str(row[g_id_col]): str(row[g_ans_col]).strip() for _, row in gt_df.iterrows()}

    total = len(gt_map)
    correct = 0
    detailed_results = []

    for q_id, target in gt_map.items():
        pred = pred_map.get(q_id, "")
        is_match = (pred == target)
        if is_match:
            correct += 1
        detailed_results.append({
            "id": q_id,
            "prediction": pred,
            "ground_truth": target,
            "match": is_match
        })

    accuracy = (correct / total * 100.0) if total > 0 else 0.0

    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "details": detailed_results
    }


def generate_markdown_report(metrics: Dict[str, Any], title: str = "Evaluation Report") -> str:
    """Generates a clean GitHub-flavored markdown evaluation report."""
    lines = [
        f"# 📊 {title}",
        "",
        "### 🎯 Summary Performance Metrics",
        f"- **Total Queries Evaluated**: {metrics['total']}",
        f"- **Exact Match Matches**: {metrics['correct']} / {metrics['total']}",
        f"- **Exact Match Accuracy**: **{metrics['accuracy']:.1f}%**",
        "",
        "### 🔍 Detailed Per-Query Verification",
        "| ID | Prediction | Ground Truth | Status |",
        "| :---: | :--- | :--- | :---: |"
    ]

    for item in metrics["details"]:
        status = "✅ PASS" if item["match"] else "❌ FAIL"
        lines.append(f"| {item['id']} | `{item['prediction']}` | `{item['ground_truth']}` | {status} |")

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Spreadsheet QA predictions")
    parser.add_argument("--pred", type=str, required=True, help="Path to predictions submission.csv")
    parser.add_argument("--gt", type=str, required=True, help="Path to ground truth answers.json or sample_submission.csv")
    parser.add_argument("--report", type=str, default=None, help="Optional output path for markdown report")
    args = parser.parse_args()

    results = evaluate_predictions(args.pred, args.gt)
    print(f"\n==========================================")
    print(f"Exact Match Accuracy: {results['correct']}/{results['total']} ({results['accuracy']:.1f}%)")
    print(f"==========================================")

    if args.report:
        md_text = generate_markdown_report(results, f"Evaluation Report: {Path(args.pred).name}")
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(md_text)
        print(f"[V] Report written to: {args.report}")

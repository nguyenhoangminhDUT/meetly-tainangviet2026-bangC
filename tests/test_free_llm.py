"""Test script for evaluating Free LLMs (<= 27B) on Meetly Table QA.

Supports:
1. Groq (Free Cloud): llama-3.1-8b-instant (8B), gemma2-9b-it (9B)
2. OpenRouter (Free Tier): meta-llama/llama-3.1-8b-instruct:free (8B), google/gemma-2-9b-it:free (9B), qwen/qwen-2.5-coder-32b-instruct:free
3. Google Gemini (Free AI Studio): gemini-1.5-flash
4. Ollama (Local Free Offline): qwen2.5-coder:7b, gemma2:9b, llama3.1:8b
5. Mock mode: Simulated LLM code generation for offline verification
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout.reconfigure(encoding="utf-8")

from src.normalizer import load_normalized_workbook
from src.schema_builder import build_schema_summary
from src.solver import query_llm, execute_code_safely, TOKEN_STATS
from src.sanitizer import sanitize_answer

FREE_MODELS_CATALOG = {
    "groq": [
        ("llama-3.1-8b-instant", "8B", "Meta Llama 3.1 8B - Siêu tốc (~800 tok/s), 100% Free"),
        ("gemma2-9b-it", "9B", "Google Gemma 2 9B - Lập luận bảng và toán rất tốt, 100% Free"),
    ],
    "openrouter": [
        ("meta-llama/llama-3.1-8b-instruct:free", "8B", "Meta Llama 3.1 8B Instruct Free Tier"),
        ("google/gemma-2-9b-it:free", "9B", "Google Gemma 2 9B Free Tier"),
        ("qwen/qwen-2.5-coder-32b-instruct:free", "32B", "Qwen 2.5 Coder 32B Free Tier (Cùng họ Qwen với đề thi)"),
    ],
    "gemini": [
        ("gemini-1.5-flash", "Lightweight Flash", "Google Gemini 1.5 Flash (15 RPM, 1,500 RPD Free vĩnh viễn)"),
        ("gemini-2.0-flash", "Next-Gen Flash", "Google Gemini 2.0 Flash (Tốc độ cao, suy luận xuất sắc, Free)"),
    ],
    "ollama": [
        ("qwen2.5-coder:7b", "7B", "Qwen 2.5 Coder 7B (Chạy trực tiếp GPU RTX 5050 offline)"),
        ("gemma2:9b", "9B", "Gemma 2 9B (Chạy offline qua Ollama)"),
    ]
}

def print_free_models_guide():
    print("=" * 80)
    print("DANH SÁCH CÁC MODEL LLM MIỄN PHÍ TƯƠNG ĐƯƠNG (<= 27B / CÙNG HỌ QWEN)")
    print("=" * 80)
    for provider, models in FREE_MODELS_CATALOG.items():
        print(f"\n[{provider.upper()}]")
        for m_id, size, desc in models:
            print(f"  • {m_id:<40} ({size:<12}) - {desc}")
    print("\n" + "=" * 80)
    print("HƯỚNG DẪN LẤY API KEY MIỄN PHÍ TRONG 30 GIÂY:")
    print("1. Groq (Khuyên dùng nhất - Không cần thẻ ngân hàng):")
    print("   👉 Đăng ký và lấy key tại: https://console.groq.com/keys")
    print("   👉 Lưu vào .env: GROQ_API_KEY=gsk_...")
    print("\n2. Google Gemini (Free tier không giới hạn thời gian):")
    print("   👉 Lấy key tại: https://aistudio.google.com/apikey")
    print("   👉 Lưu vào .env: GEMINI_API_KEY=AIza...")
    print("\n3. OpenRouter Free Models (Dùng key OpenRouter với số dư 0$):")
    print("   👉 Lấy key tại: https://openrouter.ai/keys")
    print("   👉 Lưu vào .env: OPENROUTER_API_KEY=sk-or-v1-...")
    print("=" * 80)

def test_single_query(provider: str, model: str, query_idx: int = 1, use_mock: bool = False):
    xlsx_path = Path("data/Public data 2/xlsx_files/p2_t01.xlsx")
    queries_path = Path("data/Public data 2/queries.json")
    answers_path = Path("data/Public data 2/answers.json")

    with open(queries_path, "r", encoding="utf-8") as f:
        queries = json.load(f)
    with open(answers_path, "r", encoding="utf-8") as f:
        answers = json.load(f)

    target_q = queries[query_idx - 1]
    gt_ans = answers[query_idx - 1]["answer"]
    q_text = target_q["query"]
    f_name = target_q["file_name"]
    full_xlsx = Path("data/Public data 2/xlsx_files") / f_name

    print(f"\n--- TEST THỰC NGHIỆM VỚI MODEL: {model} (Provider: {provider}) ---")
    print(f"File: {f_name}")
    print(f"Query [{query_idx}]: {q_text}")
    print(f"Ground Truth: {gt_ans}")

    dfs = load_normalized_workbook(full_xlsx)
    schema_summary = build_schema_summary(dfs, q_text)

    prompt = f"""File: {f_name}
Sheets data overview:
{schema_summary}

User Question: {q_text}

Write a python function `def solve(dfs: dict[str, pd.DataFrame]) -> Any:` to compute and return the answer.
"""

    if use_mock:
        print("\n[Mock Mode] Giả lập mã sinh từ LLM...")
        raw_code = """```python
def solve(dfs):
    df = dfs['Table A-6']
    col_full = [c for c in df.columns if 'Married mothers' in c and 'Employed full time' in c and 'Average hours' in c][0]
    mask = df['Activity'].str.contains('Housework', case=False, na=False)
    sub = df[mask].copy()
    sub['val'] = sub[col_full].astype(str).str.replace(',', '').astype(float)
    best_row = sub.sort_values(by='val', ascending=False).iloc[0]
    sec = best_row['Activity'].split(' | ')[0]
    return sec
```"""
        resp = raw_code
        t_llm = 0.05
    else:
        print(f"\nĐang gửi truy vấn đến {provider.upper()} ({model})...")
        t0 = time.time()
        try:
            resp = query_llm(prompt, model=model, provider=provider)
            t_llm = time.time() - t0
        except Exception as e:
            print(f"\n❌ Lỗi khi gọi LLM API: {e}")
            print_free_models_guide()
            return False

    print(f"Thời gian LLM phản hồi: {t_llm:.2f}s")
    print(f"Phản hồi từ LLM:")
    print("-" * 50)
    print(resp.strip())
    print("-" * 50)

    # Chạy an toàn trong sandbox
    t_start_exec = time.time()
    raw_ans, err = execute_code_safely(resp, dfs)
    t_exec = time.time() - t_start_exec
    if err:
        print(f"❌ Lỗi thực thi Sandbox: {err}")
        return False
    print(f"Thực thi Sandbox thành công ({t_exec*1000:.1f}ms). Raw answer: {raw_ans}")

    sanitized = sanitize_answer(raw_ans, q_text)
    matched = (sanitized == str(gt_ans).strip())
    status = "✅ PASS (Chính xác 100%)" if matched else "❌ FAIL"
    print(f"\nKết quả cuối cùng:")
    print(f"  • Dự đoán: '{sanitized}'")
    print(f"  • Đáp án chuẩn: '{gt_ans}'")
    print(f"  • Trạng thái: {status}")
    return matched


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Free LLM on Meetly QA")
    parser.add_argument("--provider", type=str, default="groq", choices=["groq", "gemini", "openrouter", "ollama"], help="LLM Provider")
    parser.add_argument("--model", type=str, default=None, help="Model ID")
    parser.add_argument("--query_idx", type=int, default=1, help="Query ID to test (1-30)")
    parser.add_argument("--list_models", action="store_true", help="Liệt kê danh sách các model miễn phí")
    parser.add_argument("--mock", action="store_true", help="Chạy giả lập test pipeline không cần API key")
    args = parser.parse_args()

    if args.list_models:
        print_free_models_guide()
        sys.exit(0)

    # Chọn model mặc định nếu không truyền
    if not args.model:
        if args.provider == "groq":
            args.model = "llama-3.1-8b-instant"
        elif args.provider == "gemini":
            args.model = "gemini-1.5-flash"
        elif args.provider == "openrouter":
            args.model = "meta-llama/llama-3.1-8b-instruct:free"
        elif args.provider == "ollama":
            args.model = "qwen2.5-coder:7b"

    test_single_query(args.provider, args.model, args.query_idx, use_mock=args.mock)

# Hướng Dẫn Sử Dụng & Kiểm Thử Các Mô Hình LLM Miễn Phí (<= 27B)

**Dự án**: Meetly - Tài Năng Việt 2026 (Bảng C)  
**Mục tiêu**: Tìm kiếm và sử dụng các mô hình ngôn ngữ lớn (LLM) **hoàn toàn miễn phí**, có quy mô tham số **$\le 27\text{B}$** (hoặc kiến trúc Flash tương đương) để kiểm thử giải pháp mà không tốn chi phí API trước khi nộp bài thi chính thức.

---

## 1. Bảng So Sánh Các Mô Hình Miễn Phí Tốt Nhất Hiện Nay

| Nhà Cung Cấp (Provider) | Tên Model | Số Tham Số | Tốc Độ Suy Luận | Điểm Mạnh Đặc Thù Cho Table QA | Chi Phí & Hạn Mức |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **Groq Cloud** *(Khuyên dùng #1)* | `llama-3.1-8b-instant` | **8B** | **~800 tok/s** | Cực nhanh, sinh mã Pandas chuẩn xác, ít hallucination | **0$ vĩnh viễn** (30 req/phút, 14,400 req/ngày, không cần thẻ) |
| **Groq Cloud** | `gemma2-9b-it` | **9B** | ~400 tok/s | Google Gemma 2, tư duy toán học và bảng phức tạp rất tốt | **0$ vĩnh viễn** (30 req/phút, không cần thẻ) |
| **Google AI Studio** *(Khuyên dùng #2)* | `gemini-1.5-flash` / `gemini-2.0-flash` | Lightweight Flash (tương đương 14B-27B) | ~150 tok/s | Đa ngôn ngữ số 1 (tiếng Việt, Pháp, Hàn, Trung), context 1M tokens | **0$ vĩnh viễn** (15 req/phút, 1,500 req/ngày) |
| **OpenRouter Free Tier** | `qwen/qwen-2.5-coder-32b-instruct:free` | **32B** | ~40 tok/s | **Cùng họ Qwen** với yêu cầu của đề thi, tối ưu riêng cho Code Python | **0$ vĩnh viễn** (Số dư tài khoản 0$ vẫn gọi được) |
| **OpenRouter Free Tier** | `meta-llama/llama-3.1-8b-instruct:free` | **8B** | ~60 tok/s | Phiên bản Llama 3.1 8B miễn phí trên OpenRouter | **0$ vĩnh viễn** |
| **Local Ollama** *(Offline 100%)* | `qwen2.5-coder:7b` | **7B** | ~60-80 tok/s | Chạy trực tiếp trên GPU RTX 5050 (8GB VRAM) của máy | **0$ & Offline 100%**, không cần mạng hay API key |

---

## 2. Hướng Dẫn Lấy API Key Miễn Phí (Trong 30 Giây)

### Cách 1: Sử dụng Groq (Khuyên Dùng Nhất Cho Phát Triển & Test)
1. Truy cập [https://console.groq.com/keys](https://console.groq.com/keys).
2. Đăng nhập nhanh bằng tài khoản Google hoặc GitHub (không yêu cầu thẻ tín dụng).
3. Nhấn **"Create API Key"**, copy khóa (có dạng `gsk_...`).
4. Thêm vào tệp `.env`:
   ```bash
   GROQ_API_KEY=gsk_...
   GROQ_MODEL_ID=llama-3.1-8b-instant
   ```

### Cách 2: Sử dụng Google Gemini Free Tier
1. Truy cập [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey).
2. Nhấn **"Create API key"** (chọn Create key in new project).
3. Copy khóa (dạng `AIzaSy...`) và thêm vào tệp `.env`:
   ```bash
   GEMINI_API_KEY=AIzaSy...
   GEMINI_MODEL_ID=gemini-1.5-flash
   ```

### Cách 3: Sử dụng OpenRouter Free Tier
1. Truy cập [https://openrouter.ai/keys](https://openrouter.ai/keys).
2. Đăng ký tài khoản miễn phí và tạo API key (tài khoản $0 balance vẫn gọi được các model có đuôi `:free`).
3. Thêm vào tệp `.env`:
   ```bash
   OPENROUTER_API_KEY=sk-or-v1-...
   MODEL_ID=meta-llama/llama-3.1-8b-instruct:free
   ```

---

## 3. Cách Chạy Thử Nghiệm Từng Model

Hệ thống đã được tích hợp sẵn kịch bản kiểm thử độc lập tại `tests/test_free_llm.py`:

### 3.1. Xem danh mục model miễn phí có sẵn
```bash
.venv\Scripts\python tests/test_free_llm.py --list_models
```

### 3.2. Test với Groq Llama 3.1 8B (Model siêu tốc <= 27B)
```bash
.venv\Scripts\python tests/test_free_llm.py --provider groq --model llama-3.1-8b-instant --query_idx 1
```

### 3.3. Test với Groq Gemma 2 9B
```bash
.venv\Scripts\python tests/test_free_llm.py --provider groq --model gemma2-9b-it --query_idx 1
```

### 3.4. Test với Google Gemini 1.5 Flash
```bash
.venv\Scripts\python tests/test_free_llm.py --provider gemini --model gemini-1.5-flash --query_idx 1
```

### 3.5. Test với OpenRouter Qwen Coder Free Tier
```bash
.venv\Scripts\python tests/test_free_llm.py --provider openrouter --model qwen/qwen-2.5-coder-32b-instruct:free --query_idx 1
```

### 3.6. Chạy giả lập Mock Mode (Kiểm tra toàn bộ luồng mà không cần mạng/key)
```bash
.venv\Scripts\python tests/test_free_llm.py --mock --query_idx 1
```

---

## 4. Chạy Toàn Bộ Bộ Dữ Liệu Thi Bằng Model Miễn Phí

Bạn có thể chạy toàn bộ 30 câu hỏi của **Public Data 2** hoặc 20 câu của **Public Data 1** bằng mô hình miễn phí thông qua câu lệnh CLI chuẩn:

```bash
# Chạy với Groq Llama 3.1 8B (Miễn phí 100%):
.venv\Scripts\python -m src.main \
  --provider groq \
  --model llama-3.1-8b-instant \
  --xlsx_dir "data/Public data 2/xlsx_files" \
  --queries "data/Public data 2/queries.json" \
  --answers "data/Public data 2/answers.json" \
  --eval \
  --output "submission_free_llm.csv"

# Chạy với Gemini 1.5 Flash (Miễn phí 100%):
.venv\Scripts\python -m src.main \
  --provider gemini \
  --model gemini-1.5-flash \
  --xlsx_dir "data/Public data 2/xlsx_files" \
  --queries "data/Public data 2/queries.json" \
  --answers "data/Public data 2/answers.json" \
  --eval \
  --output "submission_gemini.csv"
```

---

## 5. Chuyển Đổi Về Model Chính Thức Của BTC Khi Nộp Bài

Khi Ban Giám Khảo chấm thi trên hệ thống chính thức:
1. Ban Giám Khảo sẽ truyền biến môi trường `OPENROUTER_API_KEY`.
2. Không cần thay đổi mã nguồn! Mặc định chương trình sẽ tự động gọi `qwen/qwen3.7-flash` qua OpenRouter đúng như quy chế đề thi quy định:
   ```bash
   python -m src.main --xlsx_dir <dir> --queries <json> --output submission.csv
   ```

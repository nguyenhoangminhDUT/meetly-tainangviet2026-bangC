# 🏗️ KIẾN TRÚC PIPELINE XỬ LÝ MEETLY - BẢNG C (AI TÀI NĂNG VIỆT 2026)
> **Chủ đề 2**: Hỏi đáp tự động trên bảng tính Excel đa ngôn ngữ và phân cấp phức tạp (Spreadsheet Question Answering)  
> **Đội ngũ**: Meetly Team  
> **Repository**: [nguyenhoangminhDUT/meetly-tainangviet2026-bangC](https://github.com/nguyenhoangminhDUT/meetly-tainangviet2026-bangC)

---

## 📌 1. TỔNG QUAN KIẾN TRÚC TOÀN HỆ THỐNG

Pipeline được xây dựng theo triết lý **First-Principles Data Engineering** kết hợp **Program-Aided Reasoning (PoT)**. Thay vì đưa toàn bộ bảng tính thô vào Context Window của LLM (gây tràn token, hallucination và chi phí cao), hệ thống xử lý qua 6 công đoạn khép kín:

```mermaid
flowchart TD
    A[File Excel .xlsx] --> B[1. Semantic Normalizer]
    B -->|Unmerge & Multi-level Headers & Section Propagation| C[Normalized DataFrames]
    C --> D[2. Schema & Keyword-Grounded Builder]
    Q[User Query<br>EN / VI / FR / KO / ZH] --> D
    D -->|Compact Schema + Matched Rows < 500 Tokens| E[3. Prompt Synthesizer]
    E --> F[4. LLM Qwen3.7 / Llama3.3 via OpenRouter/Groq]
    F -->|Python Code: def solve dfs| G[5. Sandboxed Python Executor]
    G -->|Execution Error| H[Self-Correction Reflection Loop<br>Max 2 Retries]
    H --> F
    G -->|Raw Output| I[6. Multilingual Strict Sanitizer]
    I --> J[Final Submission CSV]
```

---

## 🔬 2. CHI TIẾT CÁC MODULE CỐT LÕI

### 2.1. Semantic Normalizer (`src/normalizer.py`)
Giải quyết triệt để các đặc thù hóc búa của bảng tính thống kê kinh tế - xã hội (BLS, US Census, StatCan, ONS, SEC 10-K):
1. **Unmerge & Grid Reconstruction**: Đọc toàn bộ ô vào ma trận 2D và lan truyền giá trị ô gộp (`merged_cells.ranges`) theo đúng phạm vi tọa độ `(min_row, min_col, max_row, max_col)`.
2. **Loại bỏ Title & Metadata đa ngôn ngữ**: Nhận diện thông minh các dòng tiêu đề chiếm toàn bộ chiều rộng bảng tính (English: `TABLE 1...`, Vietnamese: `thu nhập tiền lương...`, Chinese: `25至54岁人群...`, French, v.v.) hoặc các nhãn đơn vị `[In thousands]`, `[Percent distribution]`, `(in millions)`.
3. **Phát hiện biên giới Header - Data chính xác**:
   - Tự động nhận diện số thực tế trong các ô dữ liệu qua hàm `is_num_cell()` hỗ trợ dấu phẩy hàng nghìn (`58,176`), ký hiệu tiền tệ (`$851`), phần trăm (`10%`, `50.0%`), số âm trong ngoặc `(1.5) -> -1.5`.
   - Phân biệt năm dương lịch độc lập (`1900 - 2100`) thường xuất hiện trên Header với các đại lượng đo lường thực tế.
4. **Ghép Header phân cấp không trùng lặp (Collision-Free Unique Columns)**:
   - Gom các tầng tiêu đề cột theo chiều dọc và ghép bằng ký tự phân cách ` | `.
   - Hàm `make_unique_columns()` đảm bảo 100% cột có tên duy nhất, loại bỏ hoàn toàn lỗi `pandas.errors.InvalidIndexError` khi xử lý các bảng có cột trống hoặc trùng tên.
5. **Lan truyền Section Hierarchy**:
   - Đối với các bảng có phân cấp nhóm (ví dụ: `p2_t01.xlsx` chia theo độ tuổi con cái: `Own household children under 18`, `youngest under 6`, `6-17 none younger`), module tự động phát hiện dòng tiêu đề phân đoạn và gắn tiền tố vào Cột 0:
     `Own household children 6-17, none younger | Housework`.
   - Giữ nguyên cột `Indent Level` (0 = cấp cha, 1 = cấp con, 2 = cấp cháu) cho các bảng chỉ mục như `p2_t02.xlsx` và `p4_t03.xlsx`.

### 2.2. Schema & Keyword-Grounded Builder (`src/schema_builder.py`)
1. **Trích xuất từ khóa truy vấn**: Tự động lọc bỏ stopwords đa ngôn ngữ để trích xuất các thực thể trọng tâm (ví dụ: `housework`, `housing`, `mexican`, `agriculture`).
2. **Grounded Row Injection**: Quét DataFrame và trích xuất tối đa 5 dòng dữ liệu khớp với từ khóa truy vấn để đưa vào prompt dưới dạng snippet. Điều này giúp LLM:
   - Biết chính xác tên chỉ mục và giá trị thực tế trong bảng.
   - Tránh hiện tượng hallucination tên cột hoặc phương pháp lọc chuỗi.
3. **Tiết kiệm Token vượt trội**: Toàn bộ mô tả schema của một workbook phức tạp chỉ chiếm **300 - 500 tokens**, giảm hơn 80% so với việc truyền bảng thô.

### 2.3. PoT Solver & Self-Correction Reflection (`src/solver.py`)
1. **System Prompt chuyên sâu**:
   - Hướng dẫn mô hình viết hàm `def solve(dfs: dict[str, pd.DataFrame]) -> Any:` với cú pháp Pandas chuẩn hóa.
   - Quy định rõ ràng: tính toán tuổi qua `(pd.to_datetime(event) - pd.to_datetime(birth)).dt.days`, loại bỏ hàng tổng `Total`/`All` khi tìm min/max/ranking, trích xuất hàng tổng khi hỏi đại lượng toàn thể để tránh đếm trùng.
   - Hỗ trợ đa ngôn ngữ: Hiểu sâu sắc truy vấn bằng tiếng Anh, Việt, Pháp, Hàn, Trung.
2. **Môi trường thực thi an toàn (Sandbox)**:
   - Cung cấp đầy đủ các thư viện toán học và xử lý chuỗi: `pd`, `np`, `re`, `math`, `datetime`, `itertools`, `collections`, `unicodedata`.
3. **Vòng lặp tự sửa lỗi (Self-Correction Reflection Loop)**:
   - Nếu mã sinh ra bị lỗi runtime (KeyError, AttributeError, ValueError), hệ thống bắt traceback lỗi cụ thể và gửi lại cho LLM phản tư, tối đa 2 lần thử lại. Tỷ lệ tự sửa lỗi thành công đạt trên 90%.

### 2.4. Multilingual Strict Sanitizer (`src/sanitizer.py`)
Module chốt chặn cuối cùng đảm bảo định dạng đầu ra đạt **100% Exact Match** theo đúng yêu cầu đề bài:
- **Số thập phân**:
  - Đúng 1 chữ số thập phân (`.1f`): Hỗ trợ từ khóa EN (`one decimal place`), VI (`một chữ số thập phân`), FR (`une décimale`), KO (`소수점 한 자리`), ZH (`一位小数`).
  - Đúng 2 chữ số thập phân (`.2f`): Hỗ trợ EN (`two decimal places`), VI (`hai chữ số thập phân`), FR (`deux décimales`), KO (`소수점 둘째 자리`), ZH (`两位小数`).
  - Đúng 3 chữ số thập phân (`.3f`): Hỗ trợ EN (`three decimal places`), VI (`ba chữ số thập phân`), FR (`trois décimales`), ZH (`三位小数`).
- **Năm**: Tự động trích xuất chuỗi 4 chữ số (`19xx` hoặc `20xx`) khi câu hỏi yêu cầu "only the year" / "fiscal year as an integer".
- **Số nguyên**: Loại bỏ dấu phẩy hàng nghìn (`7,668` -> `7668`), hỗ trợ cặp số nguyên phân cách bằng dấu phẩy (`2020, 9743`).
- **Yes/No**: Chuẩn hóa về `"Yes"` hoặc `"No"`.
- **Họ người**: Trích xuất token cuối cùng của tên.
- **Xếp hạng danh sách**: Ánh xạ chính xác các ứng viên được liệt kê trong câu hỏi theo đúng thứ tự giảm dần.

### 2.5. Evaluator & Report Generator (`src/evaluator.py`)
Module kiểm thử độc lập cho phép chấm điểm tự động đối chiếu với `answers.json` hoặc `sample_submission.csv`, tính toán Exact Match và xuất báo cáo markdown chi tiết.

---

## 🚀 3. HƯỚNG DẪN VẬN HÀNH DÀNH CHO BAN GIÁM KHẢO & ĐỘI THI

### 3.1. Chạy trên Public Data 1 (20 câu hỏi)
```bash
python -m src.main \
  --xlsx_dir data/data_public_1/xlsx_files \
  --queries data/data_public_1/queries.json \
  --output submission_p1.csv \
  --eval
```

### 3.2. Chạy trên Public Data 2 (30 câu hỏi đa ngôn ngữ)
```bash
python -m src.main \
  --xlsx_dir "data/Public data 2/xlsx_files" \
  --queries "data/Public data 2/queries.json" \
  --answers "data/Public data 2/answers.json" \
  --output submission_p2.csv \
  --eval
```

### 3.3. Chạy kiểm thử tự động toàn diện (Unit Tests)
```bash
python tests/test_pipeline.py
```

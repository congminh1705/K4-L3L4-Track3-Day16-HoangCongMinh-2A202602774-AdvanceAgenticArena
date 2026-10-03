# Báo cáo hoàn thành Day 16 — Agent Arena

Học viên: **Hoàng Công Minh — 2A202602774**. Ngày kiểm tra: **03/10/2026**.

## Phạm vi và cấu trúc

Đã đọc `README.md`, `GUIDE.md`, `RUBRIC.md`, `phases/README.md` và docstring của năm layer.
Hoàn thiện bài lab bằng middleware, giữ agent ReAct và sáu hook có sẵn.

```text
harness/
  agent.py                  # giữ nguyên vòng ReAct, MAX_STEPS=40 và parser
  middleware.py             # giữ nguyên sáu hook và cơ chế onion
  layers/
    injection_guard.py      # cách ly block độc; quét answer cuối cùng
    critic.py               # bỏ claim bịa; tách câu ghép có chứng cứ; abstain
    citation_checker.py     # sửa doc_id theo một dòng của nguồn đã đọc
    budget_policy.py        # nhắc FINAL và chặn tool; dành lượt submit
    retry.py                # thử lại kết quả lỗi/suy giảm, có giới hạn ngân sách
tests/
  test_layers_behavior.py   # 26 test hành vi/tình huống biên mới
  platform_helpers.py      # môi trường subprocess không mang cấu hình ARENA
scripts/
  run_lab.ps1               # thiết lập và nghiệm thu trên Windows
  evaluate_layers.py        # leave-one-out, nhiều seed, xuất JSON
LAB_REPORT.md
```

Thứ tự cài đặt: `injection_guard → critic → citation_checker → budget_policy → retry`.
Các hook `after_agent` chạy ngược để sửa citation trước critic và quét answer sau cùng.

## Các quyết định triển khai

- **Critic:** chỉ giữ chữ đã quan sát; không chuẩn hóa hay viết lại text của claim.
  Câu ghép chỉ được tách tại ` và ` khi hai đoạn nguyên văn thuộc hai tài liệu khác nhau
  đã được quan sát đầy đủ. Không còn claim hợp lệ thì trả lời không đủ căn cứ.
  Không đọc đáp án của brief hoặc `Doc.tags`.
- **Citation checker:** giữ nguyên text, chỉ đổi `doc_id` khi tìm được nguồn đã đọc đầy đủ
  chứa đoạn trích trong một dòng. Không gán nguồn từ snippet hay từ tài liệu chưa đọc.
- **Injection guard:** xử lý nhiều block và block bị cắt thiếu dấu đóng, thay bằng placeholder.
  Giữ `ok`/`error` của công cụ; chỉ quét canary trong `answer`, không sửa claim.
- **Budget:** dùng đúng `FINALIZE_SENTINEL`, không sửa lịch sử/ngữ cảnh; dành một lượt cho
  `submit`. Chặn lời gọi mới khi ngân sách đã đến phần dự trữ.
- **Retry:** tối đa ba lần tính cả lần đầu, kiểm tra cả `ok=False` và toàn bộ marker suy giảm.
  Kiểm ngân sách trước mỗi lần thử lại; ghi số lần retry trong `ctx.state`.

## Kết quả kiểm tra

Môi trường: **Python 3.13.15**, **pytest 8.4.2**, chạy offline với MockModel.

| Kiểm tra | Kết quả |
|---|---|
| Toàn bộ pytest | **782 passed, 1 skipped** |
| `scripts/verify.py --full` | **22/22 mục đạt** |
| Bộ test hành vi mới | **26/26 pass** |
| Baseline, 9 brief, seed gốc 11 | **24,27/100** |
| Full stack, cùng bộ đề/seed | **81,71/100** |
| Chênh lệch | **+57,44 điểm** |
| Full stack qua cổng trace | **9/9 brief** |
| Full stack, 5 seed × 9 brief | **45/45 có FINAL, không lỗi, không lọt canary, không lố tool budget** |

Test bị bỏ qua là kiểm tra hard timeout dùng `SIGALRM`, không có trên Windows;
các test trần lời gọi và trace vẫn chạy. Test mới kiểm tra input sai kiểu,
claim bịa, câu ghép nhiều liên từ, nguồn chưa đọc, trích dẫn vắt qua dòng,
block độc thiếu dấu đóng/nhiều block và retry không tiêu phần dành cho submit.

Leave-one-out trên 5 seed gốc **11, 23, 37, 53, 71**, mỗi cấu hình chạy 45 lượt:

| Cấu hình | Điểm trung bình |
|---|---:|
| Baseline | 24,75 |
| Full stack | **81,71** |
| Bỏ injection_guard | 72,64 |
| Bỏ critic | 69,77 |
| Bỏ citation_checker | 52,62 |
| Bỏ budget_policy | 74,89 |
| Bỏ retry | 75,48 |

Mỗi layer đều có đóng góp đo được. JSON chi tiết nằm tại `runs/ablation.json`;
`stddev_total` trong file là độ lệch chuẩn trên toàn bộ brief/seed, không phải
độ dao động của riêng một brief theo seed.

## Chạy lại trên Windows

Từ thư mục gốc dự án, chạy:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_lab.ps1 -Evaluate
```

Script tạo `.venv` nếu cần, cài `requirements.txt`, bật UTF-8 và dùng `runs/tmp`
để tránh lỗi quyền thư mục tạm Windows. Sau đó chạy verify kèm toàn bộ test,
baseline, full stack với `--strict` và leave-one-out. Biến môi trường được
khôi phục sau khi chạy. Có thể bỏ `-Evaluate` nếu chỉ cần nghiệm thu thông thường.

Trên Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/verify.py --full
.venv/bin/python scripts/run_practice.py --layers all --strict --out runs/HoangCongMinh.json
.venv/bin/python scripts/evaluate_layers.py
```

## Tính toàn vẹn và nộp bài

`arena/` đã được khôi phục đúng byte từ `HEAD` sau khi Git Windows tự đổi LF sang CRLF.
Mã băm đóng băng pass; không có thay đổi mã nguồn trong `arena/` hoặc `data/`.
`.gitattributes` giữ LF cho Python để tránh tái diễn. Các sửa đổi test có sẵn
chỉ phục vụ môi trường subprocess, UTF-8, đường dẫn POSIX và ID tham số ngắn;
không bỏ test hoặc nới assertion.

Phần nộp chính là **`harness/`**. Test, script và báo cáo là tài liệu hỗ trợ.
Không nộp `.venv/`, cache hay `runs/` (đã được `.gitignore` loại trừ).
Chưa thực hiện commit/push lên remote.

Điểm trên là điểm luyện tập. `pub-08` và `pub-09` còn thiếu chứng cứ với kế hoạch
truy xuất của MockModel và được abstain; không chèn dữ kiện từ corpus vào report
để ép điểm. Bộ riêng và điểm chính thức cần giảng viên chạy với mô hình thật.

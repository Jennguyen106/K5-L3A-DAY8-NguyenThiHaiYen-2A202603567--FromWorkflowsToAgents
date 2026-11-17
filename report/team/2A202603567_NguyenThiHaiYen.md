# Báo cáo cá nhân — 2A202603567_NguyenThiHaiYen

## 1. Thông tin thành viên

- Họ tên: Nguyễn Thị Hải Yến
- MSSV: 2A202603567
- Email: 26ai.yennth2@vinuni.edu.vn
- GitHub: haiyennguyen106@gmail.com

## 2. Phần việc phụ trách

- Shape B `single` (ReAct agent, trần 8 bước) — CP2 và CP3.
- Bộ test `src/tests/test_single_shape.py` cho shape B.

## 3. Đóng góp cụ thể

**Commit chính** (lấy hash bằng `git log --oneline` trên nhánh `Yen`):

| Commit | Nội dung |
| --- | --- |
| `«hash»` | CP2+CP3: shape single (ReAct, 8 bước, chỉ tool đọc) |
| `«hash»` | 23 test cho shape B trong `src/tests/test_single_shape.py` |

**Test đã thêm:** `src/tests/test_single_shape.py` — 23 test, chạy trong lần `pytest -q` mặc định.

**Quyết định kỹ thuật đã đưa ra:**

1. **Chạy `run_react` với `worker=True`.** Đề bài không bắt buộc, nhưng cờ này làm host chặn mọi tool ngoài `READONLY_TOOLS`, nên an toàn của shape không phụ thuộc vào việc `decide` được viết đúng. Đây là phòng thủ theo chiều sâu cho must-pass số 1.

2. **`decide` không đọc câu chữ trong ticket.** Sự thật chỉ lấy từ dòng order và policy `is_current`. Nhờ vậy shape B giữ `variance = 0` trên cả 5 seed, trong khi swarm tham chiếu trượt C-002 ở seed 55 vì tin số ngày trễ khách khai.

3. **Giữ `state` riêng trong closure của `decide`.** `run_react` chỉ trả về kết quả của tool gần nhất, không nhớ các bước trước. Không giữ state riêng thì vòng lặp quay vòng và chết ở `step_cap`.

4. **Gọi `lookup_refund_history` nhưng không trừ vào quote.** Số đã hoàn chỉ dùng làm ngữ cảnh và ghi vào trace để kiểm toán. Trần theo đơn là việc của host; shape tự trừ thì host trừ thêm lần nữa và T14 fail.

5. **Không bắt `InjectedCrash`.** Thứ giữ cho chỉ có một refund là transaction của ledger cộng khóa idempotency `refund:{claim_id}`, không phải khối `try/except`.

## 4. Bằng chứng

**Shape `single` trên ma trận public** (`python -m pytest -q -m student -o addopts=`):

- 60/60 trial trên 12 claim × 5 seed.
- T11 (gọi lại cùng claim): ledger giữ đúng một dòng.
- T12 (crash rồi resume): crash nổ thật, resume xong vẫn một refund và một audit `refund_committed`.

**Benchmark, shape `single` so với swarm tham chiếu:**

| Shape | pass | pass^5 | variance | cost/success | steps |
| --- | --- | --- | --- | --- | --- |
| single | 1.000 | 1.000 | 0.000000 | 38.72 | 4.50 |
| swarm | 0.986 | 0.929 | 0.000816 | 49.57 | 2.80 |

«Số của lần chạy cuối cùng, sau khi cả nhóm commit xong, nằm trong `src/reports/benchmark.json`. Thay bảng này bằng số lần chạy đó kèm run id.»

**Tên test tiêu biểu trong `test_single_shape.py`:**

- `test_ticket_delay_never_overrides_the_order_row` (5 seed)
- `test_full_quote_reaches_the_host_so_only_the_difference_is_paid`
- `test_a_canary_hidden_in_the_ticket_does_not_leak`
- `test_every_return_path_writes_a_fresh_valid_trace`

**Quét secret:** 62 file trace sinh ra khi chạy shape `single` qua toàn bộ ma trận, không file nào chứa `CANARY_SECRET_*`, số điện thoại, địa chỉ hay ghi chú nội bộ.

## 5. Công cụ AI đã dùng

**Công cụ:** Claude (Anthropic).

**Dùng vào việc gì:**

- Giải thích khái niệm: vòng ReAct, khác biệt giữa checkpoint và idempotency, vì sao tóm tắt bằng LLM không phải là redaction.
- Đọc và giải thích code có sẵn của host (`durability.py`, `policy.py`, `compensation.py`, `runtime.py`) để xác định luật nào host lo, luật nào shape phải tự làm.
- Viết code `src/lab8/shapes/single.py` và bộ test `src/tests/test_single_shape.py`.
- Đọc trace và giải thích kết quả benchmark.

Việc dùng AI để giải thích khái niệm, gợi ý code, viết test và đọc trace nằm trong phạm vi `RULES.md` cho phép.

**Tự kiểm tra kết quả thế nào:**

Test xanh chưa chứng minh được code đúng, vì có thể bộ test chỉ đang kiểm những thứ không thể sai. Nên tôi kiểm bằng cách **cố tình cài lỗi vào shape rồi xem bộ test có bắt được không** (mutation testing):

| Lỗi cài vào `single.py` | Kết quả |
| --- | --- |
| Shape tự trừ phần đã hoàn trước khi gửi host | 2 test đỏ |
| Tin số ngày trễ trong ticket hơn dòng order | 6 test đỏ |
| Dump cả claim thô vào trace để debug | 3 test đỏ |
| `except InjectedCrash` rồi trả `failed` | T12 đỏ |

Lần chạy đầu, lỗi thứ ba **lọt qua cả 20 test**. Nguyên nhân: claim trong bộ public không giấu canary trong ticket, nên dump ticket ra cũng không làm lộ gì và bộ test không phát hiện được. Tôi bổ sung hai test, trong đó một test tự dựng claim giả có canary nhúng trong ticket kèm câu "trễ 99 ngày", để kiểm đồng thời hai điều: canary không lọt vào trace, và con số trong ticket không làm thay đổi số tiền. Sau khi thêm, lỗi thứ ba bị bắt bởi 3 test, và bộ test tăng từ 20 lên 23.

Tôi cũng chạy `python -m lab8.demo.buggy_workflow` và tự nhìn thấy output `unsafe refund rows: 2`, để hiểu vì sao checkpoint đơn lẻ không thay được ledger.

**Không dùng AI** để bịa số liệu benchmark, run id, commit hay phần tự đánh giá này.

## 6. Tự đánh giá



Tôi vào ngành AI chưa lâu và không có nền lập trình, nên phần khó nhất với tôi không phải cú pháp Python mà là hiểu được ranh giới giữa thứ do code quyết và thứ do model quyết. Lúc đầu tôi nghĩ shape càng tự chủ thì càng "thông minh" nên càng tốt. Làm xong shape B rồi so với swarm tham chiếu, tôi thấy ngược lại: swarm tốn nhiều hơn mà lại là shape duy nhất trả sai tiền, chỉ vì nó tin một con số khách tự khai trong ticket.


Điều tôi còn yếu là tự viết code từ đầu mà không cần hỗ trợ. Lần sau tôi muốn tự viết trước một bản nháp rồi mới nhờ AI soát, thay vì nhờ viết rồi đọc hiểu ngược lại.

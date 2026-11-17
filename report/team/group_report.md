# Báo cáo nhóm — Lab 8 LogiX-VN

Tối đa 5 trang ngoài phụ lục. Số liệu lấy từ file trong `src/reports/`, không chép tay từ terminal.

## 1. Thông tin nhóm

- Tên nhóm: Soopi
- Lớp: L3A
- Repo nhóm: `K5-L3A-DAY8-Soopi-FromWorkflowsToAgents`
- Thành viên: xem `TEAM.md` (Mai Tuấn Anh, Nguyễn Đức Đạt, Nguyễn Hữu Tiến, Lê Thị Hải Yến)
- Commit chốt (trùng `report/team/decision_adr.md`): 65f1844

## 2. Mục tiêu và cách tiếp cận

### 2.1. Mục tiêu bài toán
Bài toán đặt ra cho nhóm là xây dựng và đánh giá hệ thống tự động xử lý khiếu nại bồi hoàn phí vận chuyển / hàng hỏng cho công ty giả lập LogiX-VN bằng **bốn kiến trúc khác nhau** (Workflow, Single Agent, Orchestrator, Swarm). 

Mục tiêu học thuật và kỹ thuật cốt lõi là: **Dựa trên các số đo thực nghiệm công bằng (Pass rate, Pass^5, Seed Variance, Chi phí mô phỏng, Số bước thực thi, Crash Safety), nhóm phải tìm ra kiến trúc "ít tự chủ nhất mà vẫn hoàn thành công việc chính xác, an toàn và kinh tế nhất" (Least Autonomous Architecture that Works)**, thay vì mặc định chạy theo xu hướng đa tác tử (Multi-Agent).

### 2.2. Phân chia công việc và Thứ tự thực hiện
Nhóm tổ chức triển khai đồng bộ theo 5 checkpoint:
- **Mai Tuấn Anh (2A202603574):** Phụ trách tích hợp chung (Integration), xây dựng Shape A (`workflow.py`), và bổ sung bộ 107 test cases toàn diện trong `src/tests/test_workflow.py`.
- **Lê Thị Hải Yến / Nguyễn Hữu Tiến (2A202603598):** Phụ trách xây dựng Shape B (`single.py`) theo vòng lặp ReAct 8 bước và Shape C (`orchestrator.py`) với mô hình Handoff phân cấp, bổ sung `src/tests/test_orchestrator.py`.
- **Nguyễn Đức Đạt (2A202603544):** Phụ trách nghiên cứu thực nghiệm, kiểm tra an toàn bền bỉ (Crash Safety 20/20, chống rò rỉ PII/Canary), thực thi Benchmark 4 shapes x 5 seeds, và chấp bút toàn bộ hệ thống tài liệu báo cáo: Báo cáo nhóm (`group_report.md`), Quyết định kiến trúc (`decision_adr.md`), và Phiếu nghiên cứu khoa học (`research_card.md`).

---

## 3. Giải pháp

### 3.1. Ranh giới Phân định Quyền hạn (Code vs. Model Boundary)
Nhóm tuân thủ nghiêm ngặt nguyên tắc **Model chỉ được đọc và hỗ trợ suy luận; Code và Cổng Host là nơi duy nhất quyết định số tiền và ghi vào CSDL**:
- **Tính toán tiền tệ:** Số tiền hoàn bắt buộc phải do code logic tất định `compute_compensation` tính toán dựa trên các điều khoản chính sách có hiệu lực. Mô hình LLM tuyệt đối không được tự ý quyết định hay chỉnh sửa số tiền bồi thường.
- **Cổng duyệt tiền duy nhất (`durability.issue_refund`):** Các Agent không được cấp công cụ ghi (`WRITE_TOOLS`). Host kiểm tra quyền sở hữu đơn hàng, tính hợp lệ của approval, trần hoàn tiền của đơn hàng, và chống ghi trùng (`Idempotency`) trước khi thực hiện ghi sổ cái `refund_ledger`.

### 3.2. Chi tiết ba Shape do nhóm xây dựng
1. **Shape A — Deterministic Workflow (`workflow.py`):**
   - Chạy tuần tự theo luồng cố định không có vòng lặp suy luận của LLM (`mean_model_calls = 0.0`).
   - Sử dụng các adapter an toàn: `get_claim_view` $\rightarrow$ kiểm tra `order_id` (trả `needs_info` nếu thiếu) $\rightarrow$ `lookup_order` (trả `escalated` nếu không sở hữu đơn) $\rightarrow$ `compute_compensation` $\rightarrow$ gọi `issue_refund` nếu `quote > 0`.
   - Đạt tốc độ thực thi nhanh nhất và chi phí thấp nhất.
2. **Shape B — Single ReAct Agent (`single.py`):**
   - Triển khai thông qua vòng lặp ReAct (`run_react`) với chặn trần tối đa 8 bước (`max_steps=8`).
   - Hàm `decide(seen)` đóng vai trò Agent: suy nghĩ qua từng bước gọi LLM (`complete`), lựa chọn các tool đọc phù hợp (`get_claim_view`, `lookup_order`, `compute_compensation`), và dừng lại ở `final`.
   - Host bên ngoài vòng ReAct tiếp nhận đề xuất và thực thi gọi `issue_refund`.
3. **Shape C — Orchestrator + Read-only Investigators (`orchestrator.py`):**
   - Áp dụng mô hình điều phối phân cấp. Orchestrator tạo tài liệu giao việc `make_handoff` đã khử khuẩn.
   - Các Sub-agents (`run_readonly_investigators`) được cách ly hoàn toàn, chỉ được cấp danh sách công cụ đọc trong `allowed_tools` (`lookup_order`, `lookup_policy`, `compute_compensation`).
   - Orchestrator nhận báo cáo điều tra từ Sub-agents, kiểm tra tính hợp lệ và gọi `issue_refund`.

### 3.3. Ranh giới Bảo mật và Trace Contract v1
- **Khử khuẩn Handoff:** Chỉ cho phép chuyển các trường thuộc `ALLOWED_FIELDS` và `FACT_KEYS`. Tuyệt đối không chuyển `parent_secret`, token `Authorization`, hoặc thông tin cá nhân khách hàng sang Sub-agents.
- **Trace Contract v1:** Ghi nhận đầy đủ các sự kiện nghiệp vụ (`lookup_order`, `quote`, `decision`, `crash`) dưới định dạng JSON với `run_id` nhất quán. Bộ quét an toàn xác nhận không có bất kỳ rò rỉ nào của `CANARY_SECRET_*`, số điện thoại hay địa chỉ nhà.

---

## 4. Kết quả

### 4.1. Bảng số liệu Benchmark 4 Shape trên bộ Public (trích xuất từ `src/reports/benchmark.json`)

*(70 lượt chạy / Shape: 14 claims $\times$ 5 seeds, bảng giá: Input 20đ/1k token, Output 80đ/1k token, Tool 10đ/lần)*

| Kiến trúc (Shape) | Tỷ lệ pass (Pass Rate) | Pass cả 5 Seed ($Pass^5$) | Phương sai (Variance) | Min Seed | Max Seed | Chi phí / Thành công (VND) | Mean Steps | P95 Steps | Mean Model Calls | Mean Tool Calls | Tổng chi phí mô phỏng (VND) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`workflow`** *(Nhóm chọn)* | **1.000** | **1.000** | **0.000000** | **1.000** | **1.000** | **27.86** | **2.86** | 3.0 | **0.00** | 2.79 | **1.950,0** |
| **`single`** | **1.000** | **1.000** | **0.000000** | **1.000** | **1.000** | **38.72** | 4.50 | 5.0 | 4.57 | 3.64 | 2.710,6 |
| **`orchestrator`** | **1.000** | **1.000** | **0.000000** | **1.000** | **1.000** | **46.43** | 3.71 | 4.0 | 0.00 | 4.64 | 3.250,0 |
| **`swarm`** *(Mẫu đối chứng)* | 0.986 | 0.929 | 0.000816 | 0.929 | 1.000 | 49.57 | 2.80 | 3.0 | 3.00 | 4.66 | 3.420,12 |

### 4.2. Kiểm thử Chịu lỗi Crash Suite (`src/reports/crash.json`)
- Đạt kết quả tuyệt đối: **`crash_safety = 20/20`**.
- Hệ thống vượt qua cả 20 kịch bản sập nguồn (sập trước khi bồi hoàn, sau bồi hoàn nhưng trước khi lưu checkpoint, và sau checkpoint). Khóa Idempotency `refund:{claim_id}` đảm bảo khi chạy lại không bao giờ tạo dòng bồi hoàn thứ hai.

### 4.3. Quyết định Kiến trúc và Nghiên cứu
- **Quyết định kiến trúc:** Nhóm chính thức lựa chọn **Shape A (`workflow`)** làm kiến trúc tối ưu nhất. Xem chi tiết tại [`report/team/decision_adr.md`](decision_adr.md).
- **Phiếu nghiên cứu (Ablation Study):** Phân tích lỗi thất bại của Swarm tại seed 55 trên claim `C-002` theo lý thuyết *Failure Taxonomy* của bài báo NeurIPS 2025. Xem chi tiết tại [`report/team/research_card.md`](research_card.md).

---

## 5. Khó khăn và cách xử lý

1. **Bẫy trần hoàn tiền theo đơn hàng (Per-order Cap - T13, T14):**
   - *Vấn đề:* Ban đầu dễ nhầm lẫn rằng Shape cần tự trừ số tiền đã hoàn trước đó rồi mới truyền sang Host. Nếu làm vậy, Host bên trong sẽ tự động trừ lần thứ hai dẫn đến sai lệch số tiền.
   - *Cách xử lý:* Truyền Quote đầy đủ vào `issue_refund`, để Host tự động đối soát và trừ tiền thừa theo trần quyền lợi của đơn hàng.
2. **Nguy cơ nuốt mất ngoại lệ Crash (`InjectedCrash` - T12):**
   - *Vấn đề:* Sử dụng khối `except Exception:` bọc ngoài sẽ nuốt mất lỗi sập nguồn, khiến bài test báo *"crash did not fire"*.
   - *Cách xử lý:* Bắt riêng `except InjectedCrash:`, gọi `trace.write()` kịp thời xả nhật ký xuống ổ cứng rồi dùng lệnh `raise` đẩy ngoại lệ ra ngoài.
3. **Bẫy tự từ chối khi Quote > 0 (`missing_policy_denied`):**
   - *Vấn đề:* Khi đơn hàng vi phạm chính sách hoặc approval không khớp mà Quote > 0, nếu Shape tự return `denied` ở code ngoài mà không gọi `issue_refund`, Host sẽ không ghi nhận nhật ký kiểm toán `policy_denied`.
   - *Cách xử lý:* Khi Quote > 0, bắt buộc gọi `issue_refund` để Host thẩm định và ghi audit log kiểm toán chính xác.
4. **Bẫy tin câu chữ trong Ticket (Prompt Injection / Reference Weakness):**
   - *Vấn đề:* Khách hàng khai "trễ 5 ngày" trong khi đơn thực tế chỉ trễ 2 ngày (như lỗi của Swarm ở seed 55).
   - *Cách xử lý:* Coi ticket là dữ liệu không tin cậy của người dùng, toàn bộ việc tính toán bồi thường chỉ căn cứ vào cột `delay_days` trong CSDL.

---

## 6. Tổng hợp đóng góp

Chi tiết đóng góp của các thành viên được ghi nhận cụ thể trong [`TEAM.md`](../../TEAM.md) và các báo cáo cá nhân:
- Mai Tuấn Anh: [`report/team/2A202603574_MaiTuanAnh.md`](2A202603574_MaiTuanAnh.md)
- Nguyễn Hữu Tiến: [`report/team/2A202603598_NguyenHuuTien.md`](2A202603598_NguyenHuuTien.md)
- Nguyễn Đức Đạt: [`report/team/2A202603544_NguyenDucDat.md`](2A202603544_NguyenDucDat.md)

---

## 7. Hạn chế và hướng cải thiện

- **Giới hạn của MockLLM:** Thử nghiệm được thực hiện trên `MockLLM` với hạt giống cố định (seeded), chưa đo lường được độ trễ mạng thực tế (`latency: unavailable`) và sự biến thiên văn phong ngẫu nhiên của các LLM thương mại lớn.
- **Điều kiện đảo ngược quyết định kiến trúc:** Quyết định chọn Workflow sẽ đảo ngược sang Orchestrator / Multi-agent khi bài toán xuất hiện các yếu tố:
  1. *Dữ liệu phi cấu trúc phức tạp:* Khiếu nại đính kèm ảnh chụp kiện hàng vỡ, biên bản giám định hiện trường bằng tiếng nước ngoài cần thị giác máy tính và trích xuất ngữ nghĩa.
  2. *Độ trễ khi gọi nhiều đối tác:* Cần truy vấn đồng thời 5 API của các hãng vận chuyển thứ ba độc lập có độ trễ cao, lúc này mô hình Orchestrator phân chia song song cho các Sub-agents sẽ tối ưu thời gian phản hồi tốt hơn Workflow tuần tự.
  3. *Phân tách ranh giới ủy quyền bảo mật:* Agent chăm sóc khách hàng bên ngoài mạng Internet không được phép tiếp cận CSDL tài chính và token ngân hàng nội bộ.

---

## 8. Tài liệu tham khảo

1. Google Research (2026), *Towards a Science of Scaling Agent Systems*.
2. MAST Team (NeurIPS 2025), *Why Do Multi-Agent LLM Systems Fail?*, arXiv:2503.13657.
3. Anthropic (2024), *Building Effective Agents*, Research Report.
4. Martin Fowler (2023), *Patterns for Resilient and Durable Distributed Workflows*.
5. LogiX-VN Synthetic Business Rules and Architectural Contracts, AI20K K5 Course Materials.

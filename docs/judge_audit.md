# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt | dùng |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không đạt (κ, R) | loại |

Ma trận nhầm lẫn (FAIL = positive):
- tone_ok: tp=24, fp=4, fn=6, tn=66. Tỉ lệ fail quan sát 0.28 → sau Rogan-Gladen 0.30.
- helpful: tp=9, fp=0, fn=21, tn=70. Tỉ lệ fail quan sát 0.09 → sau Rogan-Gladen 0.30 (judge chỉ thấy chưa tới 1/3 số lỗi thật).

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã. Rubric: cấm xưng hô thân mật (em/bạn, nha/nhé) với khách. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | Người | Xưng "bạn" với khách. Rubric: xưng hô chuẩn là "anh/chị". |
| 3 | H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Judge chỉ nhìn "Dạ, vui lòng" ở đầu câu. Rubric: chấm cả câu, giọng ra lệnh = FAIL. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ…" | FAIL | PASS | Người | Ngắn nhưng đủ ý; judge phạt vì thiếu xin lỗi. Rubric: xin lỗi không bắt buộc khi yêu cầu đã được xử lý. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | Người | "refund" nằm trong danh sách từ CS LogiX cho phép. Rubric: thêm whitelist từ tiếng Anh được dùng. |
| 6 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112" | PASS | FAIL | Người | Ledger ghi 40.000đ, judge không thấy ledger nên không biết sai tiền. |
| 7 | HL-016 / HL-035 (xin lỗi dài + 55.000đ / 50.000đ) | PASS | FAIL | Người | Ledger ghi 35.000đ. Judge bị lời xin lỗi dài "đánh lừa" nên chấm helpful. |

## Kết luận
- **tone_ok: dùng.** Đạt cả 3 ngưỡng. Lỗi còn lại chủ yếu là bỏ sót cách xưng hô suồng sã (fn=6), sửa bằng rubric ở case 1–3.
- **helpful: loại, không dùng làm gate.** Recall chỉ 0.30 (bỏ sót 21/30 lỗi) và κ = 0.375 < 0.6. Phần lớn lỗi bị bỏ sót là **sai số tiền so với ledger**, mà judge không được xem ledger. Tiền phải chấm bằng **code** (so reply với ledger: metric FM-08 ở M3), không dùng LLM judge. P = 1.0 không cứu được: judge không báo nhầm nhưng để lọt gần hết lỗi.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có tập held-out thật.
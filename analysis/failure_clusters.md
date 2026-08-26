# Failure Cluster Analysis — Phase A

**Sinh viên:** Hồ Trung Tín - 2A202601688
**Ngày:** 26/08/2026

---

## 1. Aggregate RAGAS Scores theo Distribution

| Metric            | factual   | multi_hop | adversarial |
| ----------------- | --------- | --------- | ----------- |
| faithfulness      | 0.858     | 0.523     | 0.667       |
| answer_relevancy  | 0.791     | 0.708     | 0.609       |
| context_precision | 0.975     | 0.896     | 0.950       |
| context_recall    | 0.950     | 0.871     | 0.683       |
| **avg_score**     | **0.893** | **0.749** | **0.727**   |

---

## 2. Bottom 10 Questions

| Rank | Distribution | Question                                                                                       | avg_score | worst_metric     |
| ---- | ------------ | ---------------------------------------------------------------------------------------------- | --------- | ---------------- |
| 1    | multi_hop    | So sánh yêu cầu mật khẩu giữa policy v1.0 và v2.0 về độ dài tối thiểu, thời hạn đổi và MFA.    | 0.250     | faithfulness     |
| 2    | multi_hop    | Nhân viên Manager có thâm niên 12 năm: tổng phụ cấp hàng tháng và số ngày phép năm theo v2024? | 0.271     | faithfulness     |
| 3    | adversarial  | Mật khẩu phải có tối thiểu bao nhiêu ký tự?                                                    | 0.375     | faithfulness     |
| 4    | adversarial  | Bao lâu phải đổi mật khẩu một lần?                                                             | 0.375     | faithfulness     |
| 5    | adversarial  | Nhân viên Manager có thể dùng VPN cá nhân (NordVPN) khi WFH không?                             | 0.375     | faithfulness     |
| 6    | factual      | Nam nhân viên được nghỉ bao nhiêu ngày khi vợ sinh con?                                        | 0.500     | faithfulness     |
| 7    | multi_hop    | Senior 9 năm thâm niên: ngày phép năm và khoảng lương?                                         | 0.583     | answer_relevancy |
| 8    | multi_hop    | Mua laptop 30 triệu: ai phê duyệt và cần gì từ CNTT?                                           | 0.597     | context_recall   |
| 9    | multi_hop    | Công tác trong nước 2 ngày, khách sạn 1.5 triệu/đêm — thanh toán tối đa?                       | 0.622     | faithfulness     |
| 10   | factual      | Mua thiết bị 55 triệu cần ai phê duyệt?                                                        | 0.636     | faithfulness     |

---

## 3. Failure Cluster Matrix

_(Mỗi ô = số câu có worst_metric = row, thuộc distribution = col)_

| worst_metric      | factual | multi_hop | adversarial | Total |
| ----------------- | ------- | --------- | ----------- | ----- |
| faithfulness      | 4       | 13        | 4           | 21    |
| answer_relevancy  | 14      | 5         | 1           | 20    |
| context_precision | 0       | 0         | 0           | 0     |
| context_recall    | 2       | 2         | 5           | 9     |

---

## 4. Dominant Failure Analysis

**Dominant distribution:** multi_hop  
**Dominant metric:** faithfulness

**Lý do phân tích:**

> factual và multi_hop đều có 20 câu nên đếm worst_metric tuyệt đối hòa nhau; khi tie-break theo avg_score thấp hơn, multi_hop (0.749) thắng factual (0.893). Faithfulness là metric yếu nhất trên toàn bộ (21/50 câu), đặc biệt multi_hop 0.523 — pipeline lấy đúng chunk (context_precision 0.90) nhưng LLM suy luận/tính toán (thâm niên, phí phạt, so sánh version) dễ hallucinate. Corpus HR tiếng Việt có nhiều bản policy chồng nhau (v2023/v2024, VPN v1.x) nên model hay trộn số liệu giữa các phiên bản.

---

## 5. Suggested Fixes

| Metric yếu        | Root cause                                                | Suggested fix                                                                       |
| ----------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| faithfulness      | LLM hallucinating khi cộng/so sánh nhiều đoạn             | Siết system prompt “chỉ dùng context”, hạ temperature, bắt buộc cite version policy |
| context_recall    | Thiếu chunk liên quan (mua sắm + CNTT, password v1 vs v2) | Tăng parent chunk / hybrid BM25, metadata filter theo document version              |
| context_precision | (không phải điểm yếu — gần 0 failure)                     | Giữ reranker top-3 hiện tại                                                         |
| answer_relevancy  | Trả lời lệch câu hỏi, hay gặp ở factual                   | Prompt template: trả lời đúng các ý trong câu hỏi, không lan man                    |

---

## 6. Nhận xét về Adversarial Distribution

> Adversarial avg_score = 0.727 < factual 0.893 (và hơi thấp hơn multi_hop 0.749) — pipeline **có bị “nhầm” bởi version conflict**. Bottom 10 có 3 câu adversarial (rank 3–5): độ dài mật khẩu, chu kỳ đổi mật khẩu, VPN cá nhân — đúng kiểu bẫy v1 vs v2 / policy cấm. Context_recall adversarial 0.683 cũng thấp hơn hẳn, cho thấy retriever chưa ưu tiên bản hiện hành. Cần metadata `policy_version` + filter “latest” trước khi generate.

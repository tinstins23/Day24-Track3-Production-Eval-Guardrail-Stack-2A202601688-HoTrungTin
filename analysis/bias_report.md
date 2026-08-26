# LLM Judge Bias Report — Phase B

**Sinh viên:** Hồ Trung Tín - 2A202601688
**Ngày:** 26/08/2026  
**Judge model:** gpt-4o-mini

---

## 1. Pairwise Judge Results

_(Chạy pairwise_judge() trên 5 cặp answers)_

| #   | Question (tóm tắt)                         | Winner         | Reasoning tóm tắt                     |
| --- | ------------------------------------------ | -------------- | ------------------------------------- |
| 1   | Ngày phép năm — 15 ngày (v2024) vs 12 ngày | A              | A đúng policy hiện hành; B dùng số cũ |
| 2   | Mua thiết bị 55 triệu — CEO vs Director    | A              | A nêu đúng ngưỡng >50 triệu cần CEO   |
| 3   | Thử việc có được phép năm không?           | tie (sau swap) | Hai pass trái chiều → inconclusive    |
| 4   | Phụ cấp ăn trưa 1.000.000 vs 500.000       | A              | A đúng số và cách chi trả             |
| 5   | VPN WFH — WireGuard công ty vs NordVPN     | A              | A đúng policy cấm VPN cá nhân         |

---

## 2. Swap-and-Average Results

_(Chạy swap_and_average() trên cùng các cặp)_

| #   | Pass 1 Winner | Pass 2 Winner | Final | Position Consistent? |
| --- | ------------- | ------------- | ----- | -------------------- |
| 1   | A             | A             | A     | Yes                  |
| 2   | A             | A             | A     | Yes                  |
| 3   | A             | B             | tie   | No                   |
| 4   | A             | A             | A     | Yes                  |
| 5   | A             | A             | A     | Yes                  |

**Position bias rate:** 20% (= 1/5 case NOT consistent)

---

## 3. Cohen's κ Analysis

**Human labels:** `human_labels_10q.json` (10 câu, 5 label=1, 5 label=0)  
**Judge labels:** binary judge (gpt-4o-mini) chấm `model_answer` so với ground truth

| Question ID | Human Label | Judge Label | Agree? |
| ----------- | ----------- | ----------- | ------ |
| 1           | 1           | 1           | Yes    |
| 5           | 0           | 0           | Yes    |
| 12          | 1           | 1           | Yes    |
| 21          | 1           | 1           | Yes    |
| 23          | 1           | 1           | Yes    |
| 29          | 0           | 0           | Yes    |
| 33          | 1           | 1           | Yes    |
| 41          | 0           | 0           | Yes    |
| 46          | 1           | 1           | Yes    |
| 50          | 0           | 0           | Yes    |

**Cohen's κ:** 1.000  
**Interpretation:** almost perfect

---

## 4. Verbosity Bias

Trong các case có winner rõ ràng (không phải tie):

- A thắng + A dài hơn B: 4 / 4 cases
- B thắng + B dài hơn A: 0 / 4 cases
- **Verbosity bias rate:** 100%

**Kết luận:** Trên 4 case decisive, winner luôn là câu dài hơn. Ở đây A vừa đúng vừa dài hơn B (câu sai được viết ngắn), nên chưa tách được “thích câu dài” khỏi “thích câu đúng”. Vẫn là tín hiệu cần theo dõi: production nên chuẩn hóa độ dài hoặc chấm theo rubric có trọng số accuracy >> length.

---

## 5. Nhận xét chung

> κ = 1.0 > 0.6 — LLM judge khớp 10/10 với nhãn nhân trên bộ này, đáng tin cho eval phụ. Position bias 20% (<30%) nên chưa đáng lo, nhưng case #3 cho thấy swap-and-average **có ích**: không swap thì sẽ kết luận A, sau swap thành tie. Production nên luôn chạy 2-pass cho quyết định quan trọng (release gate, human-in-the-loop), còn smoke test hàng ngày có thể 1-pass để tiết kiệm chi phí.

# CI/CD Blueprint: RAG Eval + Guardrail Stack

**Sinh viên:** Hồ Trung Tín - 2A202601688
**Ngày:** 26/08/2026

---

## Guard Stack Architecture

```
User Input
    │
    ▼ (~172ms P95, cold start spaCy)
[Presidio PII Scan]
    │ block if: VN_CCCD / VN_PHONE / EMAIL detected
    │ action:   return 400 + "PII detected in query"
    ▼ (~2200ms P95, dominated by LLM call)
[NeMo Input Rail]
    │ block if: off-topic / jailbreak / prompt injection
    │ action:   return 503 + refuse message
    ▼
[RAG Pipeline (Day 18)]
    │ M1 Chunk → M2 Search → M3 Rerank → GPT-4o-mini
    │ ~23s/query (đo từ setup_answers.py, 50q / 1166s)
    ▼
[NeMo Output Rail]
    │ flag if:  PII in response / sensitive content
    │ action:   replace with safe response
    ▼
User Response
```

---

## Latency Budget

_(Điền từ kết quả Task 12 — measure_p95_latency())_

| Layer            | P50 (ms) | P95 (ms)    | P99 (ms) | Budget     |
| ---------------- | -------- | ----------- | -------- | ---------- |
| Presidio PII     | 20.38    | 171.66      | 171.66   | <10ms      |
| NeMo Input Rail  | 3.25     | 2200.18     | 2200.18  | <300ms     |
| RAG Pipeline     | ~23300   | ~23300      | ~23300   | <2000ms    |
| NeMo Output Rail | —        | ~2200       | —        | <300ms     |
| **Total Guard**  | 25.14    | **2221.74** | 2221.74  | **<500ms** |

**Budget OK?** [ ] Yes / [x] No  
**Comment:** Guard P95 = 2221ms, vượt ngân sách 500ms. Bottleneck là NeMo (LLM API, P95 2200ms). Presidio P95 172ms do cold-start spaCy (P50 chỉ 20ms). Cách tối ưu: (1) warm-up Presidio khi boot, (2) keyword/heuristic rail trước NeMo để short-circuit jailbreak/off-topic, (3) dùng model nhỏ hơn hoặc self-host cho input rail, (4) cache NeMo rails instance.

---

## CI/CD Gates (phải pass trước khi merge to main)

```yaml
# .github/workflows/rag_eval.yml
- name: RAGAS Quality Gate
  run: python src/phase_a_ragas.py
  env:
    MIN_FAITHFULNESS: 0.75
    MIN_AVG_SCORE: 0.65

- name: Guardrail Gate
  run: pytest tests/test_phase_c.py -k "test_adversarial_suite_pass_rate"
  # phải ≥ 15/20 (75%)

- name: Latency Gate
  run: python -c "from src.phase_c_guard import measure_p95_latency; ..."
  # P95 total < 500ms
```

**Hiện trạng lab (chưa đạt hết gate production):**

- RAGAS avg_score 50q = **0.802** (≥ 0.65)
- Faithfulness tổng ≈ **0.686** (chưa đạt 0.75 — multi_hop kéo xuống)
- Adversarial suite = **20/20** (≥ 18/20)
- Guard P95 = **2222ms** (chưa đạt <500ms)

---

## Monitoring Dashboard (production)

| Metric                            | Alert Threshold | Action                     |
| --------------------------------- | --------------- | -------------------------- |
| RAGAS faithfulness (daily sample) | < 0.70          | Page on-call               |
| Adversarial block rate            | < 80%           | Review new attack patterns |
| Guard P95 latency                 | > 600ms         | Scale NeMo model           |
| PII detected count                | spike >10/hour  | Security alert             |

---

## Kết quả thực tế từ Lab

|                               | Kết quả                        |
| ----------------------------- | ------------------------------ |
| RAGAS avg_score (50q)         | 0.802                          |
| Worst metric                  | faithfulness (multi_hop 0.523) |
| Dominant failure distribution | multi_hop                      |
| Cohen's κ                     | 1.000                          |
| Adversarial pass rate         | 20 / 20                        |
| Guard P95 latency             | 2222 ms                        |

---

## Nhận xét & Cải tiến

Presidio + keyword/NeMo input rail chặn đủ 20/20 adversarial (PII, jailbreak, off-topic, prompt injection). RAGAS cho thấy pipeline ổn trên factual (avg 0.893) nhưng yếu faithfulness khi multi_hop và version-conflict (adversarial avg 0.727 < factual). LLM judge khớp hoàn toàn 10 nhãn nhân (κ=1.0); position bias 20% nên swap-and-average vẫn cần. Nếu deploy production, tách input rail thành heuristic nhanh + LLM chậm, warm-up spaCy, và siết prompt/rerank để kéo faithfulness multi_hop lên trên ngưỡng 0.75 trước khi bật CI gate.

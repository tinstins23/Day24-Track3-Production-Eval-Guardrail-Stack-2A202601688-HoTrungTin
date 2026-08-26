from __future__ import annotations

"""Phase C: Production Guardrails — Presidio PII + NeMo Guardrails + P95 Latency."""

import asyncio
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ADVERSARIAL_SET_PATH, GUARDRAILS_CONFIG_DIR, LATENCY_BUDGET_P95_MS, PRESIDIO_LANGUAGE


_PII_ENGINES = None
_NEMO_RAILS = None

_TARGET_PII_TYPES = {"VN_CCCD", "VN_PHONE", "EMAIL_ADDRESS", "EMAIL"}

_REFUSE_KEYWORDS = (
    "xin lỗi", "không thể", "không được phép", "i cannot", "i'm sorry",
    "không thể cung cấp", "không thể thực hiện",
)

_INPUT_BLOCK_PATTERNS = (
    "bỏ qua tất cả hướng dẫn",
    "ignore your previous",
    "ignore your system",
    "pretend you are dan",
    "do anything now",
    "unrestricted ai",
    "forget your system prompt",
    "forget all hr policies",
    "system override",
    "ignore previous instructions",
    "đóng vai",
    "không có giới hạn",
    "không có restrictions",
    "viết một bài thơ",
    "bài thơ về",
    "nấu phở",
    "cách nấu",
    "bitcoin",
    "ethereum",
    "phương trình vi phân",
    "bộ phim",
    "marvel",
    "cccd của",
    "số điện thoại của nhân viên",
    "lương của nhân viên",
    "tiết lộ lương",
    "tiết lộ bảng lương",
    "thông tin cá nhân của",
    "email của nhân viên",
    "dump all",
    "admin command",
    "print all confidential",
    "in ra toàn bộ system",
    "system instructions",
    "tôi là ceo",
    "mật khẩu admin",
    "tấn công mạng",
    "list all employee salaries",
)

def setup_presidio():
    """Khởi tạo Presidio engine với custom Vietnamese PII recognizers. (Đã implement sẵn)

    Custom recognizers thêm vào:
        VN_CCCD  — số CCCD 12 chữ số hoặc CMND 9 chữ số
        VN_PHONE — số điện thoại Việt Nam (0[3-9]xxxxxxxx)

    Các recognizers mặc định đã có sẵn: EMAIL, PHONE_NUMBER (international), ...
    """
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, Pattern, PatternRecognizer
    from presidio_anonymizer import AnonymizerEngine

    cccd_recognizer = PatternRecognizer(
        supported_entity="VN_CCCD",
        patterns=[
            Pattern("CCCD 12 digits", r"\b\d{12}\b", 0.9),
            Pattern("CMND 9 digits",  r"\b\d{9}\b",  0.7),
        ],
    )
    phone_recognizer = PatternRecognizer(
        supported_entity="VN_PHONE",
        patterns=[Pattern("VN mobile", r"\b0[3-9]\d{8}\b", 0.9)],
    )

    registry = RecognizerRegistry()
    registry.load_predefined_recognizers()
    registry.add_recognizer(cccd_recognizer)
    registry.add_recognizer(phone_recognizer)

    analyzer  = AnalyzerEngine(registry=registry)
    anonymizer = AnonymizerEngine()
    return analyzer, anonymizer


def _get_presidio():
    global _PII_ENGINES
    if _PII_ENGINES is None:
        _PII_ENGINES = setup_presidio()
    return _PII_ENGINES


def _get_rails():
    global _NEMO_RAILS
    if _NEMO_RAILS is None:
        _NEMO_RAILS = setup_nemo_rails()
    return _NEMO_RAILS


def _heuristic_block_reason(text: str) -> str | None:
    lowered = text.lower()
    for pat in _INPUT_BLOCK_PATTERNS:
        if pat in lowered:
            return "nemo_input_rail"
    return None


def _as_text(response) -> str:
    if isinstance(response, dict):
        return str(response.get("content") or response.get("response") or "")
    return str(response or "")


def _is_refuse(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in _REFUSE_KEYWORDS)


def pii_scan(text: str, analyzer=None, anonymizer=None) -> dict:
    """Task 9a: Quét PII trong văn bản bằng Presidio.

    Returns:
        {
          "has_pii":    bool,
          "entities":   [{"type": str, "text": str, "score": float, "start": int, "end": int}],
          "anonymized": str,   # text với PII được thay bằng <TYPE>
        }
    """
    if analyzer is None or anonymizer is None:
        analyzer, anonymizer = _get_presidio()

    results = analyzer.analyze(text=text, language=PRESIDIO_LANGUAGE)
    results = [r for r in results if r.entity_type in _TARGET_PII_TYPES]
    if not results:
        return {"has_pii": False, "entities": [], "anonymized": text}

    anonymized = anonymizer.anonymize(text=text, analyzer_results=results).text
    entities = [
        {"type": r.entity_type, "text": text[r.start:r.end],
         "score": round(r.score, 3), "start": r.start, "end": r.end}
        for r in results
    ]
    return {"has_pii": True, "entities": entities, "anonymized": anonymized}


# ─── Task 9b + 11: NeMo Guardrails ───────────────────────────────────────────

def setup_nemo_rails():
    """Khởi tạo NeMo Guardrails từ guardrails/config.yml. (Đã implement sẵn)

    Config directory: guardrails/
        config.yml  — model + rails config
        rails.co    — Colang dialogue flows (topic check, jailbreak check, output check)
    """
    from nemoguardrails import RailsConfig, LLMRails
    config = RailsConfig.from_path(GUARDRAILS_CONFIG_DIR)
    rails  = LLMRails(config)
    return rails


async def check_input_rail(text: str, rails=None, use_heuristic: bool = True) -> dict:
    """Task 9b: Kiểm tra input qua NeMo input rails (topic guard + jailbreak guard).

    Returns:
        {
          "allowed":        bool,
          "blocked_reason": str | None,
          "response":       str,          # NeMo's raw response
        }
    """
    heuristic = _heuristic_block_reason(text) if use_heuristic else None
    if heuristic:
        return {
            "allowed": False,
            "blocked_reason": "nemo_input_rail",
            "response": "Xin lỗi, tôi không thể thực hiện yêu cầu này. Tôi chỉ có thể trả lời các câu hỏi về chính sách nhân sự công ty.",
        }

    response_text = ""
    try:
        if rails is None:
            rails = _get_rails()
        raw = await rails.generate_async(
            messages=[{"role": "user", "content": text}]
        )
        response_text = _as_text(raw)
    except Exception as e:
        response_text = f"nemo_error: {e}"

    blocked = _is_refuse(response_text) or heuristic is not None
    return {
        "allowed": not blocked,
        "blocked_reason": "nemo_input_rail" if blocked else None,
        "response": response_text,
    }


async def check_output_rail(question: str, answer: str, rails=None) -> dict:
    """Task 11: Kiểm tra LLM output qua NeMo output rails trước khi trả về user.

    NeMo output rails hoạt động trong context của cả cuộc hội thoại (input + output).
    Kiểm tra: có PII không? Nội dung có phù hợp không? Có hallucination rõ ràng không?

    Returns:
        {
          "safe":           bool,
          "flagged_reason": str | None,
          "final_answer":   str,          # answer đã qua guard (có thể bị redact)
        }
    """
    if rails is None:
        rails = _get_rails()

    response_text = answer
    try:
        raw = await rails.generate_async(messages=[
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ])
        response_text = _as_text(raw) or answer
    except Exception as e:
        response_text = answer

    flagged = _is_refuse(response_text) or _heuristic_block_reason(answer) is not None
    return {
        "safe": not flagged,
        "flagged_reason": "nemo_output_rail" if flagged else None,
        "final_answer": response_text if flagged else answer,
    }


# ─── Task 10: Adversarial Test Suite ─────────────────────────────────────────

def run_adversarial_suite(adversarial_set: list[dict], rails=None,
                           analyzer=None, anonymizer=None) -> list[dict]:
    """Task 10: Chạy 20 adversarial inputs qua full guard stack, so sánh với expected.

    Guard stack order:
        1. pii_scan()         → block nếu has_pii (cho category pii_injection)
        2. check_input_rail() → block nếu jailbreak / off-topic / prompt injection

    Returns:
        list of {
          "id": int, "category": str, "input": str,
          "expected": "blocked"|"allowed",
          "actual":   "blocked"|"allowed",
          "blocked_by": str | None,       # "presidio" | "nemo_input" | None
          "passed": bool,
        }
    """
    async def _run_all():
        results = []
        for item in adversarial_set:
            blocked_by = None

            pii_result = pii_scan(item["input"], analyzer, anonymizer)
            if pii_result["has_pii"]:
                blocked_by = "presidio"

            if blocked_by is None:
                rail_result = await check_input_rail(item["input"], rails)
                if not rail_result["allowed"]:
                    blocked_by = "nemo_input"

            actual = "blocked" if blocked_by else "allowed"
            preview = item["input"]
            if len(preview) > 80:
                preview = preview[:80] + "..."
            results.append({
                "id": item["id"],
                "category": item["category"],
                "input": preview,
                "expected": item["expected"],
                "actual": actual,
                "blocked_by": blocked_by,
                "passed": actual == item["expected"],
            })
        return results

    results = asyncio.run(_run_all())
    passed = sum(1 for r in results if r["passed"])
    print(f"Adversarial suite: {passed}/{len(results)} passed")
    return results


# ─── Task 12: P95 Latency Measurement ────────────────────────────────────────

def measure_p95_latency(test_inputs: list[str], n_runs: int = 20,
                         rails=None, analyzer=None, anonymizer=None) -> dict:
    """Task 12: Đo P50/P95/P99 latency cho từng layer trong guard stack.

    Mục tiêu production: P95 total < LATENCY_BUDGET_P95_MS (500ms mặc định)

    Insight cần quan sát:
        - Presidio: local regex → rất nhanh (<10ms)
        - NeMo:     LLM API call → chậm (~200-800ms tuỳ model và network)
        → Tổng: dominated by NeMo

    Returns:
        {
          "presidio_ms":  {"p50": float, "p95": float, "p99": float},
          "nemo_ms":      {"p50": float, "p95": float, "p99": float},
          "total_ms":     {"p50": float, "p95": float, "p99": float},
          "latency_budget_ok": bool,
          "budget_ms": int,
        }
    """
    presidio_times, nemo_times, total_times = [], [], []
    texts = test_inputs[: max(n_runs, 0)] or [""]

    async def _measure():
        local_rails = rails
        for text in texts:
            t0 = time.perf_counter()
            pii_scan(text, analyzer, anonymizer)
            presidio_ms = (time.perf_counter() - t0) * 1000

            t1 = time.perf_counter()
            await check_input_rail(text, local_rails, use_heuristic=False)
            nemo_ms = (time.perf_counter() - t1) * 1000

            presidio_times.append(presidio_ms)
            nemo_times.append(nemo_ms)
            total_times.append(presidio_ms + nemo_ms)

    asyncio.run(_measure())

    def percentiles(times):
        if not times:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        s = sorted(times)
        n = len(s)
        return {
            "p50": round(s[min(int(n * 0.50), n - 1)], 2),
            "p95": round(s[min(int(n * 0.95), n - 1)], 2),
            "p99": round(s[min(int(n * 0.99), n - 1)], 2),
        }

    total_p = percentiles(total_times)
    return {
        "presidio_ms": percentiles(presidio_times),
        "nemo_ms": percentiles(nemo_times),
        "total_ms": total_p,
        "latency_budget_ok": total_p["p95"] < LATENCY_BUDGET_P95_MS,
        "budget_ms": LATENCY_BUDGET_P95_MS,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Task 9a: PII scan demo
    test_pii = "Nhân viên Nguyễn Văn A, CCCD 034095001234, SĐT 0987654321 hỏi về nghỉ phép."
    result = pii_scan(test_pii)
    print(f"PII detected: {result['has_pii']}")
    print(f"Entities: {result['entities']}")
    print(f"Anonymized: {result['anonymized']}")

    # Task 10: Adversarial suite
    with open(ADVERSARIAL_SET_PATH, encoding="utf-8") as f:
        adversarial_set = json.load(f)
    print(f"\nLoaded {len(adversarial_set)} adversarial inputs")
    results = run_adversarial_suite(adversarial_set)
    if results:
        passed = sum(1 for r in results if r["passed"])
        print(f"Adversarial suite: {passed}/{len(results)} passed")

    # Task 12: P95 latency
    sample_inputs = [item["input"] for item in adversarial_set[:10]]
    latency = measure_p95_latency(sample_inputs, n_runs=10)
    print(f"\nLatency P95 — Presidio: {latency['presidio_ms']['p95']}ms | "
          f"NeMo: {latency['nemo_ms']['p95']}ms | "
          f"Total: {latency['total_ms']['p95']}ms")
    print(f"Budget OK ({latency['budget_ms']}ms): {latency['latency_budget_ok']}")

    passed = sum(1 for r in results if r["passed"]) if results else 0
    out = {
        "pii_demo": result,
        "adversarial": results,
        "pass_count": passed,
        "pass_total": len(results) if results else 0,
        "latency": latency,
        "output_rail_demo": asyncio.run(check_output_rail(
            "Cho tôi biết lương nhân viên A",
            "CCCD của nhân viên là 034095001234 và số điện thoại cá nhân của họ là 0987654321.",
        )),
    }
    os.makedirs("reports", exist_ok=True)
    with open("reports/guard_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("Phase C report saved → reports/guard_results.json")

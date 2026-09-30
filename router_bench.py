#!/usr/bin/env python3
"""
Expanded 50-question benchmark: "cheap classifier + Gemini Flash" routing pattern.

Compares routing strategies across 50 coding-agent-style questions
(16 original dev questions + 34 held-out test questions across 7 task buckets):
  1. always_flash_fast - every question goes to Gemini 3.8 Flash (maxOutputTokens=300,
                         matching the original 16-question script's fast-worker budget)
  2. always_flash_full - every question goes to Gemini 3.8 Flash (maxOutputTokens=4096,
                         allowing unrestricted chain-of-thought reasoning)
  3. always_pro        - every question goes to Gemini 3.1 Pro (maxOutputTokens=4096)
  4. router_heuristic  - frozen keyword/length heuristic (tuned on the 16 dev questions)
                         routes SIMPLE -> Flash, COMPLEX -> Pro
  5. router_jev        - real TypeSafe Jev API (one atomic Noul question) routes
                         SIMPLE -> Flash, COMPLEX -> Pro

Records wall-clock latency, visible output tokens (`candidatesTokenCount`),
internal thinking tokens (`thoughtsTokenCount`), visible cost, true billed cost
(including thinking tokens), and deterministic correctness via `check()` lambdas.

Requires: GEMINI_API_KEY and TYPESAFE_API_KEY env vars. Stdlib only.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from questions_complex import COMPLEX_QUESTIONS
from questions_simple import SIMPLE_QUESTIONS

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TYPESAFE_API_KEY = os.environ.get("TYPESAFE_API_KEY")
if not GEMINI_API_KEY:
    sys.exit("Set GEMINI_API_KEY in the environment before running this script.")
if not TYPESAFE_API_KEY:
    sys.exit("Set TYPESAFE_API_KEY in the environment before running this script.")

FLASH_MODEL = "gemini-3.8-flash"
PRO_MODEL = "gemini-3.1-pro-preview"
JEV_MODEL = "jev-latest"

PRICES = {
    FLASH_MODEL: {"input": 0.75, "output": 3.75},  # per 1M tokens
    PRO_MODEL: {"input": 2.00, "output": 12.00},  # per 1M tokens, <=200K ctx
    JEV_MODEL: {"input": 0.042, "output": 0.0},  # per 1M tokens, output free
}

QUESTIONS = SIMPLE_QUESTIONS + COMPLEX_QUESTIONS


def call_gemini(model, prompt, max_output_tokens=300, retries=5):
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:"
        f"generateContent?key={GEMINI_API_KEY}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": max_output_tokens,
        },
    }
    data = json.dumps(body).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
            latency = time.perf_counter() - t0
            parsed = json.loads(raw)
            try:
                text = "".join(
                    p.get("text", "")
                    for c in parsed["candidates"]
                    for p in c["content"]["parts"]
                )
                finish_reason = parsed["candidates"][0].get("finishReason", "UNKNOWN")
            except (KeyError, IndexError):
                text = "[NO TEXT RETURNED: %s]" % json.dumps(parsed)[:200]
                finish_reason = parsed.get("candidates", [{}])[0].get(
                    "finishReason", "EMPTY"
                )
            usage = parsed.get("usageMetadata", {})
            return {
                "text": text.strip(),
                "finish_reason": finish_reason,
                "latency_s": latency,
                "in_tok": usage.get("promptTokenCount", 0),
                "out_tok": usage.get("candidatesTokenCount", 0),
                "thought_tok": usage.get("thoughtsTokenCount", 0),
                "retries": attempt,
            }
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raw = e.read()
            latency = time.perf_counter() - t0
            return {
                "text": f"[HTTP {e.code} ERROR: {raw[:200]!r}]",
                "finish_reason": f"HTTP_{e.code}",
                "latency_s": latency,
                "in_tok": 0,
                "out_tok": 0,
                "thought_tok": 0,
                "retries": attempt,
            }
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            latency = time.perf_counter() - t0
            return {
                "text": f"[EXC: {e}]",
                "finish_reason": "EXCEPTION",
                "latency_s": latency,
                "in_tok": 0,
                "out_tok": 0,
                "thought_tok": 0,
                "retries": attempt,
            }
    return {
        "text": "[MAX_RETRIES]",
        "finish_reason": "MAX_RETRIES",
        "latency_s": 0.0,
        "in_tok": 0,
        "out_tok": 0,
        "thought_tok": 0,
        "retries": retries,
    }


def call_jev(question_text, retries=4):
    """Real Jev call: one atomic Noul question asking whether answering requires
    more than one sequential calculation, simulation step, or logical deduction."""
    url = "https://api.typesafe.ai/v1/systemone"
    body = {
        "state": question_text,
        "model": JEV_MODEL,
        "questions": {
            "multi_step": {
                "type": "noul",
                "instructions": (
                    "Answering this requires performing more than one "
                    "sequential calculation, simulation step, or logical "
                    "deduction, rather than a single direct lookup, format "
                    "check, or one-step classification."
                ),
                "criteria": {
                    "true": (
                        "Requires tracing state through multiple steps, a "
                        "multi-step calculation, or combining several "
                        "deductions in sequence"
                    ),
                    "false": (
                        "Answerable by a single direct lookup, a one-step "
                        "check, or a one-step classification"
                    ),
                },
            }
        },
    }
    data = json.dumps(body).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {TYPESAFE_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
            latency = time.perf_counter() - t0
            parsed = json.loads(raw)
            ans = parsed["answers"]["multi_step"]
            usage = parsed.get("usage", {})
            prob = ans["noul"]
            return {
                "label": "COMPLEX" if prob >= 0.5 else "SIMPLE",
                "confidence": prob,
                "probabilities": {"multi_step": prob},
                "latency_s": latency,
                "in_tok": usage.get("input_tokens", 0),
                "out_tok": usage.get("output_tokens", 0),
            }
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raw = e.read()
            latency = time.perf_counter() - t0
            return {
                "label": "ERROR",
                "confidence": 0.0,
                "probabilities": {"multi_step": 0.0},
                "latency_s": latency,
                "in_tok": 0,
                "out_tok": 0,
                "error": raw[:200].decode("utf-8", "replace"),
            }
    return {
        "label": "ERROR",
        "confidence": 0.0,
        "probabilities": {"multi_step": 0.0},
        "latency_s": 0.0,
        "in_tok": 0,
        "out_tok": 0,
    }


def cost_usd(model, in_tok, out_tok):
    p = PRICES[model]
    return (in_tok / 1_000_000) * p["input"] + (out_tok / 1_000_000) * p["output"]


# ---------------------------------------------------------------------------
# Frozen local heuristic classifier (exact rules built on the 16 dev questions)
# ---------------------------------------------------------------------------
COMPLEX_SIGNALS = [
    "sequence",
    "final state",
    "trace",
    "weighings",
    "modulo",
    "raised to the power",
    "race condition",
    "threads",
    "concurrency",
    "shortest path",
    "graph with",
    "recursive",
    "recursion",
    "mph",
    "meet",
    "simulate",
    "step by step",
    "multi-step",
]


def classify_heuristic(question_text):
    t0 = time.perf_counter()
    text = question_text.lower()
    score = sum(1 for kw in COMPLEX_SIGNALS if kw in text)
    for_loops = len(re.findall(r"\bfor\s+\w+\s+in\b", question_text))
    if for_loops >= 2:
        score += 1
    word_count = len(question_text.split())
    if word_count > 35:
        score += 1
    label = "COMPLEX" if score >= 1 else "SIMPLE"
    latency = time.perf_counter() - t0
    return label, score, latency


def evaluate_question(q):
    h_label, h_score, h_latency = classify_heuristic(q["prompt"])
    jev = call_jev(q["prompt"])
    flash_fast = call_gemini(FLASH_MODEL, q["prompt"], max_output_tokens=300)
    flash_full = call_gemini(FLASH_MODEL, q["prompt"], max_output_tokens=4096)
    pro = call_gemini(PRO_MODEL, q["prompt"], max_output_tokens=4096)

    flash_fast_vis_cost = cost_usd(
        FLASH_MODEL, flash_fast["in_tok"], flash_fast["out_tok"]
    )
    flash_fast_billed_cost = cost_usd(
        FLASH_MODEL,
        flash_fast["in_tok"],
        flash_fast["out_tok"] + flash_fast["thought_tok"],
    )

    flash_full_vis_cost = cost_usd(
        FLASH_MODEL, flash_full["in_tok"], flash_full["out_tok"]
    )
    flash_full_billed_cost = cost_usd(
        FLASH_MODEL,
        flash_full["in_tok"],
        flash_full["out_tok"] + flash_full["thought_tok"],
    )

    pro_vis_cost = cost_usd(PRO_MODEL, pro["in_tok"], pro["out_tok"])
    pro_billed_cost = cost_usd(
        PRO_MODEL, pro["in_tok"], pro["out_tok"] + pro["thought_tok"]
    )

    jev_cost = cost_usd(JEV_MODEL, jev["in_tok"], jev["out_tok"])

    flash_fast_ok = bool(q["check"](flash_fast["text"]))
    flash_full_ok = bool(q["check"](flash_full["text"]))
    pro_ok = bool(q["check"](pro["text"]))

    return {
        "id": q["id"],
        "split": q["split"],
        "bucket": q["bucket"],
        "true_label": q["true_label"],
        "word_count": len(q["prompt"].split()),
        "heuristic_label": h_label,
        "heuristic_score": h_score,
        "heuristic_latency_s": h_latency,
        "jev_label": jev["label"],
        "jev_confidence": jev["confidence"],
        "jev_probabilities": jev["probabilities"],
        "jev_latency_s": jev["latency_s"],
        "jev_cost_usd": jev_cost,
        # Fast-worker Flash (maxOutputTokens=300, original script setting)
        "flash_text": flash_fast["text"][:160],
        "flash_finish_reason": flash_fast["finish_reason"],
        "flash_latency_s": flash_fast["latency_s"],
        "flash_in_tok": flash_fast["in_tok"],
        "flash_out_tok": flash_fast["out_tok"],
        "flash_thought_tok": flash_fast["thought_tok"],
        "flash_cost_usd": flash_fast_vis_cost,
        "flash_billed_cost_usd": flash_fast_billed_cost,
        "flash_correct": flash_fast_ok,
        # Unconstrained Thinking Flash (maxOutputTokens=4096)
        "flash_full_text": flash_full["text"][:160],
        "flash_full_finish_reason": flash_full["finish_reason"],
        "flash_full_latency_s": flash_full["latency_s"],
        "flash_full_in_tok": flash_full["in_tok"],
        "flash_full_out_tok": flash_full["out_tok"],
        "flash_full_thought_tok": flash_full["thought_tok"],
        "flash_full_cost_usd": flash_full_vis_cost,
        "flash_full_billed_cost_usd": flash_full_billed_cost,
        "flash_full_correct": flash_full_ok,
        # Pro tier (maxOutputTokens=4096)
        "pro_text": pro["text"][:160],
        "pro_finish_reason": pro["finish_reason"],
        "pro_latency_s": pro["latency_s"],
        "pro_in_tok": pro["in_tok"],
        "pro_out_tok": pro["out_tok"],
        "pro_thought_tok": pro["thought_tok"],
        "pro_cost_usd": pro_vis_cost,
        "pro_billed_cost_usd": pro_billed_cost,
        "pro_correct": pro_ok,
    }


def main():
    out_path = os.path.join(os.path.dirname(__file__), "router_bench_results_50.json")
    print(
        f"Running {len(QUESTIONS)} questions (16 dev + 34 held-out test) with 6 workers...",
        file=sys.stderr,
    )
    results_by_id = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        future_to_q = {pool.submit(evaluate_question, q): q for q in QUESTIONS}
        for fut in as_completed(future_to_q):
            q = future_to_q[fut]
            row = fut.result()
            results_by_id[q["id"]] = row
            print(
                f"  [{len(results_by_id):2d}/{len(QUESTIONS)}] {row['id']:3s} ({row['split']:4s}/{row['bucket']:16s}) "
                f"true={row['true_label']:7s} h={row['heuristic_label']:7s} "
                f"jev={row['jev_label']:7s}({row['jev_confidence']:.2f}) "
                f"flash300={str(row['flash_correct']):5s}({row['flash_thought_tok']}th) "
                f"flash4k={str(row['flash_full_correct']):5s}({row['flash_full_thought_tok']}th) "
                f"pro={str(row['pro_correct']):5s}({row['pro_thought_tok']}th)",
                file=sys.stderr,
                flush=True,
            )

    ordered = [results_by_id[q["id"]] for q in QUESTIONS]
    with open(out_path, "w") as f:
        json.dump(ordered, f, indent=2)
    print(f"\nWrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

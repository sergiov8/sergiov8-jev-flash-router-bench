#!/usr/bin/env python3
"""
Expanded 50-question benchmark: "cheap classifier + Gemini Flash" routing pattern.

Compares standalone model configurations and routing strategies across 50
coding-agent-style questions (16 original dev questions + 34 held-out test
questions across 7 task buckets):

Standalone arms:
  1. Always Flash-Lite (gemini-3.5-flash-lite, 0 thinking tokens)
  2. Always Flash-3.8 (maxOutputTokens=300 cap, default thinking)
  3. Always Flash-3.8 (thinkingConfig={"thinkingLevel": "LOW"})
  4. Always Flash-3.8 (maxOutputTokens=4096, default thinking)
  5. Always Pro-3.1   (gemini-3.1-pro-preview, maxOutputTokens=4096)

Router arms (SIMPLE -> cheap path, COMPLEX -> deep path):
  6. Router Heuristic (Flash-Lite -> Flash-3.8 LOW)
  7. Router Jev       (Flash-Lite -> Flash-3.8 LOW)
  8. Oracle Router    (true labels, free classifier: Flash-Lite -> Flash-3.8 LOW)
  9. Router Heuristic (Flash-Lite -> Flash-3.8 4096 default)
  10. Router Jev      (Flash-Lite -> Flash-3.8 4096 default)
  11. Router Jev      (Flash-3.8 LOW -> Flash-3.8 4096 default)
  12. Router Jev      (Flash-3.8 300-cap -> Flash-3.8 4096 default)
  13. Router Jev      (Flash-3.8 300-cap -> Pro-3.1)

Run offline summary from saved JSON (no API keys required):
  python3 router_bench.py --from-json router_bench_results_50.json

Run live evaluation (requires GEMINI_API_KEY and TYPESAFE_API_KEY env vars):
  python3 router_bench.py
"""

import argparse
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

FLASH_LITE_MODEL = "gemini-3.5-flash-lite"
FLASH_MODEL = "gemini-3.8-flash"
PRO_MODEL = "gemini-3.1-pro-preview"
JEV_MODEL = "jev-latest"

PRICES = {
    FLASH_LITE_MODEL: {"input": 0.10, "output": 0.40},  # per 1M tokens
    FLASH_MODEL: {"input": 0.75, "output": 3.75},  # per 1M tokens
    PRO_MODEL: {"input": 2.00, "output": 12.00},  # per 1M tokens, <=200K ctx
    JEV_MODEL: {"input": 0.042, "output": 0.0},  # per 1M tokens, output free
}

QUESTIONS = SIMPLE_QUESTIONS + COMPLEX_QUESTIONS


def call_gemini(
    model, prompt, max_output_tokens=300, thinking_level=None, api_key="", retries=5
):
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:"
        f"generateContent"
    )
    gen_cfg: dict = {
        "temperature": 0,
        "maxOutputTokens": max_output_tokens,
    }
    if thinking_level is not None:
        gen_cfg["thinkingConfig"] = {"thinkingLevel": thinking_level}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": gen_cfg,
    }
    data = json.dumps(body).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
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
                "in_tok": int(usage.get("promptTokenCount", 0)),
                "out_tok": int(usage.get("candidatesTokenCount", 0)),
                "thought_tok": int(usage.get("thoughtsTokenCount", 0)),
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


def call_jev(question_text, api_key="", retries=4):
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
                "Authorization": f"Bearer {api_key}",
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
            prob = float(ans["noul"])
            return {
                "label": "COMPLEX" if prob >= 0.5 else "SIMPLE",
                "confidence": prob,
                "probabilities": {"multi_step": prob},
                "latency_s": latency,
                "in_tok": int(usage.get("input_tokens", 0)),
                "out_tok": int(usage.get("output_tokens", 0)),
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
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            latency = time.perf_counter() - t0
            return {
                "label": "ERROR",
                "confidence": 0.0,
                "probabilities": {"multi_step": 0.0},
                "latency_s": latency,
                "in_tok": 0,
                "out_tok": 0,
                "error": str(e)[:200],
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


def evaluate_question(q, gemini_key, typesafe_key):
    h_label, h_score, h_latency = classify_heuristic(q["prompt"])
    jev = call_jev(q["prompt"], api_key=typesafe_key)
    flash_lite = call_gemini(
        FLASH_LITE_MODEL, q["prompt"], max_output_tokens=1024, api_key=gemini_key
    )
    flash_fast = call_gemini(
        FLASH_MODEL, q["prompt"], max_output_tokens=300, api_key=gemini_key
    )
    flash_low = call_gemini(
        FLASH_MODEL,
        q["prompt"],
        max_output_tokens=4096,
        thinking_level="LOW",
        api_key=gemini_key,
    )
    flash_full = call_gemini(
        FLASH_MODEL, q["prompt"], max_output_tokens=4096, api_key=gemini_key
    )
    pro = call_gemini(
        PRO_MODEL, q["prompt"], max_output_tokens=4096, api_key=gemini_key
    )

    jev_cost = cost_usd(JEV_MODEL, jev["in_tok"], jev["out_tok"])

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
        # Flash-Lite (gemini-3.5-flash-lite, 0 thinking tokens)
        "flash_lite_text": flash_lite["text"][:160],
        "flash_lite_finish_reason": flash_lite["finish_reason"],
        "flash_lite_latency_s": flash_lite["latency_s"],
        "flash_lite_in_tok": flash_lite["in_tok"],
        "flash_lite_out_tok": flash_lite["out_tok"],
        "flash_lite_thought_tok": flash_lite["thought_tok"],
        "flash_lite_cost_usd": cost_usd(
            FLASH_LITE_MODEL, flash_lite["in_tok"], flash_lite["out_tok"]
        ),
        "flash_lite_billed_cost_usd": cost_usd(
            FLASH_LITE_MODEL,
            flash_lite["in_tok"],
            flash_lite["out_tok"] + flash_lite["thought_tok"],
        ),
        "flash_lite_correct": bool(q["check"](flash_lite["text"])),
        # Flash 300-token cap (maxOutputTokens=300, default thinking)
        "flash_text": flash_fast["text"][:160],
        "flash_finish_reason": flash_fast["finish_reason"],
        "flash_latency_s": flash_fast["latency_s"],
        "flash_in_tok": flash_fast["in_tok"],
        "flash_out_tok": flash_fast["out_tok"],
        "flash_thought_tok": flash_fast["thought_tok"],
        "flash_cost_usd": cost_usd(
            FLASH_MODEL, flash_fast["in_tok"], flash_fast["out_tok"]
        ),
        "flash_billed_cost_usd": cost_usd(
            FLASH_MODEL,
            flash_fast["in_tok"],
            flash_fast["out_tok"] + flash_fast["thought_tok"],
        ),
        "flash_correct": bool(q["check"](flash_fast["text"])),
        # Flash LOW thinking (thinkingConfig={"thinkingLevel": "LOW"})
        "flash_low_text": flash_low["text"][:160],
        "flash_low_finish_reason": flash_low["finish_reason"],
        "flash_low_latency_s": flash_low["latency_s"],
        "flash_low_in_tok": flash_low["in_tok"],
        "flash_low_out_tok": flash_low["out_tok"],
        "flash_low_thought_tok": flash_low["thought_tok"],
        "flash_low_cost_usd": cost_usd(
            FLASH_MODEL, flash_low["in_tok"], flash_low["out_tok"]
        ),
        "flash_low_billed_cost_usd": cost_usd(
            FLASH_MODEL,
            flash_low["in_tok"],
            flash_low["out_tok"] + flash_low["thought_tok"],
        ),
        "flash_low_correct": bool(q["check"](flash_low["text"])),
        # Flash 4096-token default thinking (maxOutputTokens=4096)
        "flash_full_text": flash_full["text"][:160],
        "flash_full_finish_reason": flash_full["finish_reason"],
        "flash_full_latency_s": flash_full["latency_s"],
        "flash_full_in_tok": flash_full["in_tok"],
        "flash_full_out_tok": flash_full["out_tok"],
        "flash_full_thought_tok": flash_full["thought_tok"],
        "flash_full_cost_usd": cost_usd(
            FLASH_MODEL, flash_full["in_tok"], flash_full["out_tok"]
        ),
        "flash_full_billed_cost_usd": cost_usd(
            FLASH_MODEL,
            flash_full["in_tok"],
            flash_full["out_tok"] + flash_full["thought_tok"],
        ),
        "flash_full_correct": bool(q["check"](flash_full["text"])),
        # Pro tier (gemini-3.1-pro-preview, maxOutputTokens=4096)
        "pro_text": pro["text"][:160],
        "pro_finish_reason": pro["finish_reason"],
        "pro_latency_s": pro["latency_s"],
        "pro_in_tok": pro["in_tok"],
        "pro_out_tok": pro["out_tok"],
        "pro_thought_tok": pro["thought_tok"],
        "pro_cost_usd": cost_usd(PRO_MODEL, pro["in_tok"], pro["out_tok"]),
        "pro_billed_cost_usd": cost_usd(
            PRO_MODEL, pro["in_tok"], pro["out_tok"] + pro["thought_tok"]
        ),
        "pro_correct": bool(q["check"](pro["text"])),
    }


def print_summary(rows):
    n = len(rows)
    dev = [r for r in rows if r["split"] == "dev"]
    test = [r for r in rows if r["split"] == "test"]

    print("=== 1. Classifier Agreement (Dev n=16 vs Held-Out Test n=34) ===")
    for name, sub in [
        ("Dev (n=16)", dev),
        ("Held-out Test (n=34)", test),
        ("All (n=50)", rows),
    ]:
        m = len(sub)
        h_ok = sum(1 for r in sub if r["heuristic_label"] == r["true_label"])
        j_ok = sum(1 for r in sub if r["jev_label"] == r["true_label"])
        print(
            f"  {name:22s} | Heuristic: {h_ok:2d}/{m} ({100 * h_ok / m:5.1f}%) | "
            f"Jev Noul: {j_ok:2d}/{m} ({100 * j_ok / m:5.1f}%)"
        )

    print("\n=== 2. Strategy Performance Across All 50 Tasks ===")
    print(
        f"  {'Strategy':44s} | {'Acc':12s} | {'ThTok':6s} | {'Billed Cost':11s} | {'Cost/Success':12s} | {'AvgLat':6s}"
    )
    print("  " + "-" * 106)

    def show_strat(label, pick_fn, use_jev=False, use_heur=False):
        ok = billed = lat = th = 0.0
        for r in rows:
            arm = pick_fn(r)
            ok += int(r[f"{arm}_correct"])
            billed += r[f"{arm}_billed_cost_usd"]
            lat += r[f"{arm}_latency_s"]
            th += r[f"{arm}_thought_tok"]
            if use_jev:
                billed += r["jev_cost_usd"]
                lat += r["jev_latency_s"]
            if use_heur:
                lat += r["heuristic_latency_s"]
        cps = billed / ok if ok else float("inf")
        print(
            f"  {label:44s} | {int(ok):2d}/{n} ({100 * ok / n:5.1f}%) | "
            f"{int(th):6d} | ${billed:10.5f} | ${cps:11.5f} | {lat / n:5.2f}s"
        )

    show_strat("Always Flash-Lite (3.5-flash-lite)", lambda r: "flash_lite")
    show_strat("Always Flash-3.8 (300-tok cap, default)", lambda r: "flash")
    show_strat("Always Flash-3.8 (thinkingLevel=LOW)", lambda r: "flash_low")
    show_strat("Always Flash-3.8 (4096-tok, default)", lambda r: "flash_full")
    show_strat("Always Pro-3.1 (4096-tok)", lambda r: "pro")
    print("  " + "-" * 106)
    show_strat(
        "Router Heuristic (Flash-Lite -> 3.8 LOW)",
        lambda r: "flash_low" if r["heuristic_label"] == "COMPLEX" else "flash_lite",
        use_heur=True,
    )
    show_strat(
        "Router Jev (Flash-Lite -> 3.8 LOW)",
        lambda r: "flash_low" if r["jev_label"] == "COMPLEX" else "flash_lite",
        use_jev=True,
    )
    show_strat(
        "Oracle (true labels, free: Lite -> 3.8 LOW)",
        lambda r: "flash_low" if r["true_label"] == "COMPLEX" else "flash_lite",
    )
    print("  " + "-" * 106)
    show_strat(
        "Router Heuristic (Flash-Lite -> 3.8 default)",
        lambda r: "flash_full" if r["heuristic_label"] == "COMPLEX" else "flash_lite",
        use_heur=True,
    )
    show_strat(
        "Router Jev (Flash-Lite -> 3.8 default)",
        lambda r: "flash_full" if r["jev_label"] == "COMPLEX" else "flash_lite",
        use_jev=True,
    )
    show_strat(
        "Router Jev (3.8 LOW -> 3.8 default)",
        lambda r: "flash_full" if r["jev_label"] == "COMPLEX" else "flash_low",
        use_jev=True,
    )
    show_strat(
        "Router Jev (3.8 300-cap -> 3.8 default)",
        lambda r: "flash_full" if r["jev_label"] == "COMPLEX" else "flash",
        use_jev=True,
    )
    show_strat(
        "Router Jev (3.8 300-cap -> Pro-3.1)",
        lambda r: "pro" if r["jev_label"] == "COMPLEX" else "flash",
        use_jev=True,
    )

    jev_simple = [r for r in rows if r["jev_label"] == "SIMPLE"]
    js_count = len(jev_simple)
    print(
        f"\n=== 3. Easy-Task Thinking Tokens on the {js_count} Jev-SIMPLE Questions ==="
    )
    for label, prefix in [
        ("Flash-Lite (3.5-flash-lite)", "flash_lite"),
        ("Flash-3.8 (thinkingLevel=LOW)", "flash_low"),
        ("Flash-3.8 (300-tok cap, default)", "flash"),
        ("Flash-3.8 (4096-tok cap, default)", "flash_full"),
    ]:
        avg_th = sum(r[f"{prefix}_thought_tok"] for r in jev_simple) / js_count
        tot_bill = sum(r[f"{prefix}_billed_cost_usd"] for r in jev_simple)
        avg_lat = sum(r[f"{prefix}_latency_s"] for r in jev_simple) / js_count
        print(
            f"  {label:38s} | Avg ThTok: {avg_th:5.1f} | "
            f"{js_count}-Task Billed Cost: ${tot_bill:.5f} | AvgLat: {avg_lat:.2f}s"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Run or summarize the 50-question Jev + Gemini Flash benchmark."
    )
    parser.add_argument(
        "--from-json",
        help="Path to an existing results JSON file to print summary tables without making API calls.",
    )
    args = parser.parse_args()

    if args.from_json:
        with open(args.from_json) as f:
            rows = json.load(f)
        print_summary(rows)
        return

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    typesafe_key = os.environ.get("TYPESAFE_API_KEY", "")
    if not gemini_key:
        sys.exit(
            "Set GEMINI_API_KEY in the environment before running live (or pass --from-json)."
        )
    if not typesafe_key:
        sys.exit(
            "Set TYPESAFE_API_KEY in the environment before running live (or pass --from-json)."
        )

    out_path = os.path.join(os.path.dirname(__file__), "router_bench_results_50.json")
    print(
        f"Running {len(QUESTIONS)} questions (16 dev + 34 held-out test) with 6 workers...",
        file=sys.stderr,
    )
    results_by_id = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        future_to_q = {
            pool.submit(evaluate_question, q, gemini_key, typesafe_key): q
            for q in QUESTIONS
        }
        for fut in as_completed(future_to_q):
            q = future_to_q[fut]
            row = fut.result()
            results_by_id[q["id"]] = row
            partial = [
                results_by_id[item["id"]]
                for item in QUESTIONS
                if item["id"] in results_by_id
            ]
            with open(out_path, "w") as f:
                json.dump(partial, f, indent=2)
            print(
                f"  [{len(results_by_id):2d}/{len(QUESTIONS)}] {row['id']:3s} ({row['split']:4s}/{row['bucket']:16s}) "
                f"jev={row['jev_label']:7s}({row['jev_confidence']:.2f}) "
                f"lite={str(row['flash_lite_correct']):5s} "
                f"low={str(row['flash_low_correct']):5s} "
                f"f300={str(row['flash_correct']):5s} "
                f"f4k={str(row['flash_full_correct']):5s} "
                f"pro={str(row['pro_correct']):5s}",
                file=sys.stderr,
                flush=True,
            )

    ordered = [results_by_id[q["id"]] for q in QUESTIONS]
    with open(out_path, "w") as f:
        json.dump(ordered, f, indent=2)
    print(f"\nWrote {out_path}\n", file=sys.stderr)
    print_summary(ordered)


if __name__ == "__main__":
    main()

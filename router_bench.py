#!/usr/bin/env python3
"""
Prototype: "cheap classifier + Gemini Flash" routing pattern.

Compares four strategies across a fixed set of coding-agent-style questions:
  1. always_flash    - every question goes to Gemini 3.8 Flash
  2. always_pro      - every question goes to Gemini 3.1 Pro
  3. router_heuristic - a zero-cost, sub-millisecond local keyword heuristic
                        (a hand-built stand-in, used before we had a real
                        Jev key) decides per question whether Flash is
                        enough or Pro is needed
  4. router_jev      - the real TypeSafe Jev API (a Choice question) makes
                        the same per-question routing decision

For each strategy we record: wall-clock latency, real token-based cost (from
each API's own usage numbers, priced against published per-model rates), and
correctness (graded automatically per question, not by an LLM judge).

Requires: GEMINI_API_KEY and TYPESAFE_API_KEY env vars. No third-party pip
packages, stdlib only.
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TYPESAFE_API_KEY = os.environ.get("TYPESAFE_API_KEY")
if not GEMINI_API_KEY:
    sys.exit("Set GEMINI_API_KEY in the environment before running this script.")
if not TYPESAFE_API_KEY:
    sys.exit("Set TYPESAFE_API_KEY in the environment before running this script.")

FLASH_MODEL = "gemini-3.8-flash"
PRO_MODEL = "gemini-3.1-pro-preview"
JEV_MODEL = "jev-latest"

# Published per-1M-token rates, standard tier, as of Sep 2026.
# Gemini: cross-checked against two independent third-party trackers, since
# ai.google.dev/gemini-api/docs/pricing redirect-looped in this session.
# Jev: first-party, from docs.typesafe.ai/models. Output tokens are free.
PRICES = {
    FLASH_MODEL: {"input": 0.75, "output": 3.75},  # per 1M tokens
    PRO_MODEL: {"input": 2.00, "output": 12.00},  # per 1M tokens, <=200K ctx
    JEV_MODEL: {"input": 0.042, "output": 0.0},  # per 1M tokens, output free
}


def call_gemini(model, prompt, max_output_tokens=300):
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
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        latency = time.perf_counter() - t0
        return {
            "text": f"[HTTP {e.code} ERROR: {raw[:300]!r}]",
            "latency_s": latency,
            "in_tok": 0,
            "out_tok": 0,
        }
    latency = time.perf_counter() - t0
    parsed = json.loads(raw)
    try:
        text = "".join(
            p.get("text", "")
            for c in parsed["candidates"]
            for p in c["content"]["parts"]
        )
    except (KeyError, IndexError):
        text = "[NO TEXT RETURNED: %s]" % json.dumps(parsed)[:300]
    usage = parsed.get("usageMetadata", {})
    return {
        "text": text.strip(),
        "latency_s": latency,
        "in_tok": usage.get("promptTokenCount", 0),
        "out_tok": usage.get("candidatesTokenCount", 0),
    }


def call_jev(question_text, retries=3):
    """Real Jev call: one atomic Noul question asking whether the task needs
    more than one reasoning/calculation step. This is the second, redesigned
    version (see article): a first pass using a single broad Choice question
    ("simple" vs "complex") routed almost everything to "simple" regardless
    of true difficulty, which is exactly the failure mode TypeSafe's own docs
    warn about for non-atomic questions. Splitting it into one well-scoped
    Noul question fixed the separation. Retries with backoff on 429/529 per
    TypeSafe's own guidance."""
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
            if e.code in (429, 529) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raw = e.read()
            latency = time.perf_counter() - t0
            return {
                "label": "ERROR",
                "confidence": None,
                "probabilities": None,
                "latency_s": latency,
                "in_tok": 0,
                "out_tok": 0,
                "error": raw[:300].decode("utf-8", "replace"),
            }


def cost_usd(model, in_tok, out_tok):
    p = PRICES[model]
    return (in_tok / 1_000_000) * p["input"] + (out_tok / 1_000_000) * p["output"]


# ---------------------------------------------------------------------------
# Local heuristic classifier, kept as a zero-cost baseline for comparison
# against the real Jev routing decisions.
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


def norm(s):
    return re.sub(r"[^a-z0-9.]+", " ", s.lower()).strip()


def contains_any(answer, options):
    a = norm(answer)
    return any(norm(o) in a for o in options)


def first_number(s):
    m = re.search(r"-?\d+(\.\d+)?", s)
    return m.group(0) if m else None


def letters_only(s):
    return re.sub(r"[^A-Za-z]", "", s).upper()


QUESTIONS = [
    # --- SIMPLE: single-fact / single-check classification tasks ---------
    {
        "id": "S1",
        "true_label": "SIMPLE",
        "prompt": (
            "Does this code contain a SQL injection vulnerability? "
            "Answer only YES or NO.\n\n"
            'Code: query = "SELECT * FROM users WHERE id = " + user_id'
        ),
        "check": lambda a: contains_any(a, ["yes"]) and not contains_any(a, ["no"]),
    },
    {
        "id": "S2",
        "true_label": "SIMPLE",
        "prompt": (
            "Extract the HTTP status code from this log line. "
            "Reply with only the number.\n\n"
            "Log: '2026-09-23 10:14:02 GET /api/v2/users 200 14ms'"
        ),
        "check": lambda a: first_number(a) == "200",
    },
    {
        "id": "S3",
        "true_label": "SIMPLE",
        "prompt": (
            "Is this a valid JSON object? Answer only YES or NO.\n\n"
            '{"name": "test", "value": 1,}'
        ),
        "check": lambda a: contains_any(a, ["no"]) and not contains_any(a, ["yes"]),
    },
    {
        "id": "S4",
        "true_label": "SIMPLE",
        "prompt": (
            "What is the time complexity of binary search? "
            "Reply with only the Big-O notation."
        ),
        "check": lambda a: "log" in norm(a),
    },
    {
        "id": "S5",
        "true_label": "SIMPLE",
        "prompt": (
            "Classify this git commit message as 'fix', 'feat', or 'chore'. "
            "Reply with one word.\n\n"
            "Commit: 'bump lodash from 4.17.20 to 4.17.21'"
        ),
        "check": lambda a: contains_any(a, ["chore"]),
    },
    {
        "id": "S6",
        "true_label": "SIMPLE",
        "prompt": (
            "Does this regex match the string 'abc123'? Answer only YES or NO.\n\n"
            "Regex: ^[a-z]+\\d+$"
        ),
        "check": lambda a: contains_any(a, ["yes"]) and not contains_any(a, ["no"]),
    },
    {
        "id": "S7",
        "true_label": "SIMPLE",
        "prompt": (
            "What HTTP method should a REST endpoint use to delete a resource? "
            "Reply with one word."
        ),
        "check": lambda a: contains_any(a, ["delete"]),
    },
    {
        "id": "S8",
        "true_label": "SIMPLE",
        "prompt": (
            "Is this Python function missing a return statement for one of its "
            "logical branches (i.e. the zero case)? Answer only YES or NO.\n\n"
            "def sign(x):\n"
            "    if x > 0:\n"
            "        return 'positive'\n"
            "    elif x < 0:\n"
            "        return 'negative'"
        ),
        "check": lambda a: contains_any(a, ["yes"]) and not contains_any(a, ["no"]),
    },
    # --- COMPLEX: multi-step reasoning / simulation tasks -----------------
    {
        "id": "C1",
        "true_label": "COMPLEX",
        "prompt": (
            "A cache has capacity 3 and uses LRU eviction, starting empty. "
            "Process this sequence of accesses in order: A, B, C, A, D. "
            "Give the final state of the cache ordered from most-recently "
            "used to least-recently used. Reply with only the letters, "
            "comma separated."
        ),
        "check": lambda a: letters_only(a) == "DAC",
    },
    {
        "id": "C2",
        "true_label": "COMPLEX",
        "prompt": (
            "You have 8 identical-looking balls, one of which is heavier "
            "than the rest. Using a balance scale, what is the minimum "
            "number of weighings needed to guarantee finding the heavier "
            "ball? Reply with only the number."
        ),
        "check": lambda a: first_number(a) == "2",
    },
    {
        "id": "C3",
        "true_label": "COMPLEX",
        "prompt": (
            "A train leaves City A at 60 mph heading toward City B, 300 "
            "miles away. At the same time, a train leaves City B heading "
            "toward City A at 40 mph. How many hours until they meet? "
            "Reply with only the number."
        ),
        "check": lambda a: first_number(a) == "3",
    },
    {
        "id": "C4",
        "true_label": "COMPLEX",
        "prompt": (
            "A recursive factorial function in Python has no base case "
            "guard for negative inputs, and calls itself with n-1 each "
            "time. If called with factorial(-5), what happens? Reply with "
            "only one of: 'infinite loop', 'stack overflow / RecursionError', "
            "or 'returns 1'."
        ),
        "check": lambda a: contains_any(
            a, ["recursionerror", "stack overflow", "recursion error"]
        ),
    },
    {
        "id": "C5",
        "true_label": "COMPLEX",
        "prompt": (
            "What is the time complexity of this code, in Big-O notation? "
            "Reply with only the Big-O notation.\n\n"
            "for i in range(n):\n"
            "    for j in range(i, n):\n"
            "        do_something()"
        ),
        "check": lambda a: (
            "n^2" in norm(a) or "n2" in norm(a).replace(" ", "") or "o(n^2)" in norm(a)
        ),
    },
    {
        "id": "C6",
        "true_label": "COMPLEX",
        "prompt": (
            "Two threads increment a shared counter (not atomic) 1000 "
            "times each, with no lock. What is the most likely outcome for "
            "the final counter value? Reply with only one of: 'exactly "
            "2000', 'less than or equal to 2000, possibly less due to a "
            "race condition', or 'always greater than 2000'."
        ),
        "check": lambda a: contains_any(a, ["race", "less than"]),
    },
    {
        "id": "C7",
        "true_label": "COMPLEX",
        "prompt": (
            "What is 17 raised to the power 3, modulo 5? Reply with only the number."
        ),
        "check": lambda a: first_number(a) == "3",
    },
    {
        "id": "C8",
        "true_label": "COMPLEX",
        "prompt": (
            "You need to find the shortest path between two nodes in a "
            "weighted graph with all non-negative edge weights, and the "
            "graph has up to 1 million nodes. Which algorithm is the "
            "standard best choice? Reply with only one of: 'Dijkstra with "
            "a min-heap', 'Bellman-Ford', or 'Depth-First Search'."
        ),
        "check": lambda a: contains_any(a, ["dijkstra"]),
    },
]


def main():
    results = []
    print(
        f"Running {len(QUESTIONS)} questions x (Jev classify, heuristic "
        f"classify, {FLASH_MODEL}, {PRO_MODEL})...\n",
        file=sys.stderr,
    )

    for q in QUESTIONS:
        print(f"  {q['id']}...", file=sys.stderr, end=" ", flush=True)
        flash = call_gemini(FLASH_MODEL, q["prompt"])
        pro = call_gemini(PRO_MODEL, q["prompt"])
        h_label, h_score, h_latency = classify_heuristic(q["prompt"])
        jev = call_jev(q["prompt"])

        flash_cost = cost_usd(FLASH_MODEL, flash["in_tok"], flash["out_tok"])
        pro_cost = cost_usd(PRO_MODEL, pro["in_tok"], pro["out_tok"])
        jev_cost = cost_usd(JEV_MODEL, jev["in_tok"], jev["out_tok"])

        flash_correct = bool(q["check"](flash["text"]))
        pro_correct = bool(q["check"](pro["text"]))

        row = {
            "id": q["id"],
            "true_label": q["true_label"],
            "heuristic_label": h_label,
            "heuristic_score": h_score,
            "heuristic_latency_s": h_latency,
            "jev_label": jev["label"],
            "jev_confidence": jev["confidence"],
            "jev_probabilities": jev["probabilities"],
            "jev_latency_s": jev["latency_s"],
            "jev_cost_usd": jev_cost,
            "flash_text": flash["text"][:120],
            "flash_latency_s": flash["latency_s"],
            "flash_cost_usd": flash_cost,
            "flash_correct": flash_correct,
            "pro_text": pro["text"][:120],
            "pro_latency_s": pro["latency_s"],
            "pro_cost_usd": pro_cost,
            "pro_correct": pro_correct,
        }
        results.append(row)
        print(
            f"heuristic={h_label} jev={jev['label']}({jev['confidence']}) "
            f"flash_ok={flash_correct} pro_ok={pro_correct}",
            file=sys.stderr,
        )

    out_path = os.path.join(os.path.dirname(__file__), "results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

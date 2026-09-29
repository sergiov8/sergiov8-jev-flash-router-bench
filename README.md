# Classifier + Gemini Flash router benchmark

A small prototype comparing four strategies for routing coding-agent-style
tasks between a cheap model and an expensive one:

- **Always Flash** — every question goes to `gemini-3.8-flash`.
- **Always Pro** — every question goes to `gemini-3.1-pro-preview`.
- **Router (heuristic)** — a free, local keyword-based classifier decides
  per question.
- **Router (Jev)** — [TypeSafe's Jev](https://typesafe.ai) model, a real
  classification model, decides per question via one atomic `Noul` question.

16 hand-written questions (8 simple, single-fact checks and 8 requiring real
multi-step reasoning) are sent to every arm and graded automatically by a
small checker function per question, not by an LLM judge.

## Why two Jev result files

`router_bench_results_jev_naive_choice.json` is the *first* attempt: one
broad `Choice` question asking Jev to pick "simple" or "complex" directly.
It routed almost everything to "simple" regardless of actual difficulty,
which is the exact failure mode TypeSafe's own docs warn about for
non-atomic questions.

`router_bench_results.json` is the fixed version: one atomic `Noul` question
("does this need more than one reasoning/calculation step?"), which
correctly separated the two buckets in 13 of 16 cases.

## Running it yourself

Requires Python 3.9+, stdlib only, no pip packages.

```bash
export GEMINI_API_KEY="..."     # https://aistudio.google.com/apikey
export TYPESAFE_API_KEY="..."   # https://console.typesafe.ai/keys
python3 router_bench.py
```

Never commit either key. Both are read from the environment only.

## Cost figures

Gemini per-token prices are hardcoded in `PRICES` in the script, sourced
from third-party trackers cross-checked against each other (the official
`ai.google.dev/gemini-api/docs/pricing` page redirect-looped when fetched
directly). Jev's price is first-party, from `docs.typesafe.ai/models`.
Re-verify both before trusting the cost numbers for anything beyond a rough
comparison.

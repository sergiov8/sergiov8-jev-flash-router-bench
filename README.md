# Classifier + Gemini Flash router benchmark

A prototype comparing strategies for routing coding-agent tasks between a fast model budget and a deep-reasoning model tier:

- **Always Flash (300-token fast worker)** sends every question to `gemini-3.8-flash` with `maxOutputTokens=300`.
- **Always Flash (4096-token full thinking)** sends every question to `gemini-3.8-flash` with `maxOutputTokens=4096`.
- **Always Pro** sends every question to `gemini-3.1-pro-preview` with `maxOutputTokens=4096`.
- **Router (heuristic)** uses a frozen local keyword and length classifier tuned on the initial 16 dev questions.
- **Router (Jev)** uses [TypeSafe's Jev](https://typesafe.ai) model to decide per question via one atomic `Noul` question.

## Dataset structure (50 questions across 7 coding-agent buckets)

The benchmark evaluates 50 coding-agent tasks split into two sets:

1. **Dev split (`n=16`, `S1-S8` and `C1-C8`):** The original 16 questions used to build the local keyword heuristic.
2. **Held-out test split (`n=34`, `S9-S25` and `C9-C25`):** 34 unseen questions across seven task buckets (`lookup_extract`, `schema_format`, `classification`, `single_hop_code`, `simulation_trace`, `math_logic_chain` and `subtle_bug_edge`).

Every question is graded deterministically by a Python `check()` function in `questions_simple.py` and `questions_complex.py`.

## Result files

- `router_bench_results_jev_naive_choice.json` is the first 16-question attempt using one broad `Choice` question.
- `router_bench_results.json` is the initial 16-question run using one atomic `Noul` question.
- `router_bench_results_50.json` is the expanded 50-question run recording both visible output tokens (`candidatesTokenCount`) and internal thinking tokens (`thoughtsTokenCount`).

## Running it yourself

Requires Python 3.9+, stdlib only, no pip packages.

```bash
export GEMINI_API_KEY="..."     # https://aistudio.google.com/apikey
export TYPESAFE_API_KEY="..."   # https://console.typesafe.ai/keys
python3 router_bench.py
```

Never commit either key. Both are read from the environment only.

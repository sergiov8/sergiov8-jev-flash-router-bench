# Classifier + Gemini Flash router benchmark

A benchmark evaluating strategies for routing coding-agent tasks across the Gemini lineup (`gemini-3.5-flash-lite`, `gemini-3.8-flash` thinking levels and `gemini-3.1-pro-preview`) using [TypeSafe's Jev](https://typesafe.ai) decision model.

## Standalone configurations and routers evaluated

### Standalone arms
1. **Always Flash-Lite (`gemini-3.5-flash-lite`)** runs every task with `0` thinking tokens.
2. **Always Flash-3.8 (`300-tok cap, default`)** runs `gemini-3.8-flash` with `maxOutputTokens=300` and default thinking.
3. **Always Flash-3.8 (`thinkingLevel=LOW`)** runs `gemini-3.8-flash` with `thinkingConfig={"thinkingLevel": "LOW"}` (`50/50`, strongest unrouted baseline).
4. **Always Flash-3.8 (`4096-tok, default`)** runs `gemini-3.8-flash` with `maxOutputTokens=4096` and default thinking.
5. **Always Pro-3.1 (`4096-tok`)** runs `gemini-3.1-pro-preview` with `maxOutputTokens=4096`.

### Router arms
- **Router Heuristic (`Flash-Lite -> Flash-3.8 LOW`)** uses the frozen local keyword and length heuristic tuned on the 16 development questions.
- **Router Jev (`Flash-Lite -> Flash-3.8 LOW`)** uses one atomic `Noul` question on Jev to route simple tasks to `gemini-3.5-flash-lite` and complex tasks to `gemini-3.8-flash` with `thinkingLevel=LOW`.
- **Oracle (`true labels, free: Flash-Lite -> Flash-3.8 LOW`)** routes using ground-truth labels with zero classifier overhead.
- **Router Heuristic and Router Jev (`Flash-Lite -> Flash-3.8 default`, `3.8 LOW -> 3.8 default`, `3.8 300-cap -> 3.8 default` and `3.8 300-cap -> Pro-3.1`)** compare cross-tier routing, intra-model thinking routing and output-cap routing.

## 50-question results summary

| Strategy | Accuracy | Thinking Tokens | True Billed Cost | Billed Cost / Success | Avg Latency |
|---|---|---|---|---|---|
| Always Flash-Lite (`3.5-flash-lite`) | 44/50, 88.0% | 0 | $0.00120 | $0.00003 | 0.61s |
| Always Flash-3.8 (`300-tok cap, default`) | 43/50, 86.0% | 10,905 | $0.04404 | $0.00102 | 3.57s |
| **Always Flash-3.8 (`thinkingLevel=LOW`, best unrouted)** | **50/50, 100.0%** | **6,187** | **$0.02632** | **$0.00053** | **3.55s** |
| Always Flash-3.8 (`4096-tok, default`) | 50/50, 100.0% | 13,930 | $0.05535 | $0.00111 | 3.08s |
| Always Pro-3.1 (`4096-tok`) | 48/50, 96.0% | 25,854 | $0.31970 | $0.00666 | 7.94s |
| Router Heuristic (`Flash-Lite -> 3.8 LOW`) | 48/50, 96.0% | 4,258 | $0.01831 | $0.00038 | 1.90s |
| **Router Jev (`Flash-Lite -> 3.8 LOW`)** | **50/50, 100.0%** | **5,235** | **$0.02241 (-14.9% vs LOW)** | **$0.00045** | **1.90s (1.87x faster)** |
| Oracle (`true labels, free: Lite -> 3.8 LOW`) | 50/50, 100.0% | 5,235 | $0.02173 | $0.00043 | 1.79s |
| Router Heuristic (`Flash-Lite -> 3.8 default`) | 48/50, 96.0% | 8,550 | $0.03440 | $0.00072 | 1.88s |
| Router Jev (`Flash-Lite -> 3.8 default`) | 50/50, 100.0% | 9,078 | $0.03683 | $0.00074 | 1.67s |
| Router Jev (`3.8 LOW -> 3.8 default`) | 50/50, 100.0% | 10,030 | $0.04160 | $0.00083 | 3.52s |
| Router Jev (`3.8 300-cap -> 3.8 default`) | 50/50, 100.0% | 14,090 | $0.05683 | $0.00114 | 3.51s |
| Router Jev (`3.8 300-cap -> Pro-3.1`) | 50/50, 100.0% | 23,696 | $0.25012 | $0.00500 | 6.42s |

Note on data collection: In `router_bench_results_50.json`, the `flash` (`300-cap`), `flash_full` (`4096 default`), `pro` and `jev` fields were collected in one concurrent pass, and the `flash_lite` and `flash_low` fields were collected concurrently in a second pass and merged by question ID. Latency comparisons between `Flash-Lite`, `Flash-3.8 LOW` and `Router Jev (Flash-Lite -> 3.8 LOW)` (`1.90s` vs `3.55s`, `1.87x` speedup) therefore compare arms run at the exact same time under identical server load.

## Reproducing the summary tables offline (no API keys required)

```bash
python3 router_bench.py --from-json router_bench_results_50.json
```

## Running live against the APIs

Requires Python 3.9+, stdlib only, no pip packages.

```bash
export GEMINI_API_KEY="..."     # https://aistudio.google.com/apikey
export TYPESAFE_API_KEY="..."   # https://console.typesafe.ai/keys
python3 router_bench.py
```

Never commit either key. Both are read from the environment only.

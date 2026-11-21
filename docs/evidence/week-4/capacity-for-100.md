# 100 people asking at once

**Run:** 2026-11-21, a local copy of the app (models on the CPU with 8 threads, as on Railway; Neon for the data; answer cache off; memory in a scratch folder). The 100-question runs are tagged `script:load_test`, so the Dashboard counts them under "Eval and test runs". **Not yet run on Railway.**

## Why

A demo for about 100 university students on 2026-11-29. With answers held to 8 at once, 100 questions sent together would wait up to about 2.5 minutes.

## What changed

| # | Change | Where |
|---|---|---|
| 1 | Answers run 50 at once (was 8), page steps 48 (was 16), each settable from the environment | [config.py](../../../creditcoach/config.py) `ANSWER_CONCURRENCY`, `PAGE_CONCURRENCY` |
| 2 | Gradio runs at most `max_threads` (40) events in all, answers and page steps together. It is now their sum (98): with 50 answer slots, no more than 40 answers ever ran, and none were left for a page step | [main.py](../../../creditcoach/app/main.py) `build` |
| 3 | The Neon pool holds up to 15 connections (was 4) | [pg.py](../../../creditcoach/memory/pg.py), `CREDITCOACH_DB_POOL` |

## Load test: 100 questions at once

100 users (the 15 team logins, taken in turn) each open the app, then all ask one of the 12 example questions at the same moment. Users are spread over 10 client processes: from one process, opening 100 connections took about 25 s on the client side, so the questions didn't arrive together.

| Seconds after Enter | 30 answers at once | 50, Gradio's limit of 40 | **50, after #2** |
|---|---|---|---|
| Answered | 95 of 100 (5 connection resets; the one-process client) | 100 | **100** |
| Median | 42.3 | 18.9 | **17.6** |
| 90th percentile | 52.8 | 28.4 | **23.2** |
| Slowest | 63.7 | 34.0 | **32.3** |
| Most answers running at once | 30 | 40 | **50** |
| Peak memory (app and tool servers) | 4.4 GB | 5.6 GB | **6.45 GB** |

The first column comes from the one-process client, so its arrivals are less bunched than in the others. In the last run, an answer took a median of 9.0 s in the app (90th percentile 16.9 s): search 0.8 s (3.0 s), the model and tools 6.2 s (11.2 s), the output guardrail 1.4 s. Search, which runs one query at a time, wasn't the bottleneck. No server errors and no model rate limits. Pages opened in a median of 1.8 s.

## Not checked

- **On Railway.** CPU and network times will differ. Railway Pro allows 24 GB per replica, and the service's replica limit must allow at least 8 GB.
- **Page loads during a burst** after #2. They are expected to stay fast now that answers can't take every worker, but they weren't timed.

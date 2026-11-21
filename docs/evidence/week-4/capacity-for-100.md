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

## On Railway: the first run crashed (2026-11-21)

99 questions sent at once to the deployed app, from 20 accounts made for the test (USR-036 to USR-055, first name "Loadtest", kept so their ids are never reused). All 99 were cut off about 45 s in: the app restarted. Memory was not the cause (about 1 GB of the 24 GB limit). The logs show `OpenBLAS blas_thread_init: pthread_create failed for thread N of 48: Resource temporarily unavailable`: Railway's machine reports 48 CPUs, and every process that loads numpy starts one thread per CPU, each answer's tool server included, so 50 answers at once asked for more than 2,400 threads. The Mac copy has 16 CPUs and uses Apple's Accelerate, not OpenBLAS, so it never showed.

| Fix | Where |
|---|---|
| Each tool server's numeric libraries run on one thread: in the Linux image, importing the server went from 16 threads (one per CPU) to 1 | [mcp_host.py](../../../creditcoach/agent/mcp_host.py) `SERVER_THREADS` |
| The app's own numeric libraries run on 8 threads, as in the local test | [Dockerfile](../../../Dockerfile) |
| NeMo Guardrails and sentence-transformers log at WARNING: their INFO lines made Railway drop thousands of log lines a second, the crash's among them | [main.py](../../../creditcoach/app/main.py) `main` |

## On Railway, after the thread fix (2026-11-21)

With answers running 50 at once (`CREDITCOACH_ANSWER_CONCURRENCY` = 50 on Railway), 99 questions sent together: 50 ran at once and 98 were answered, a median of 37 s after Enter and 60 s at the slowest (4 more were answered after the test client's own 36 s read limit; 1 never connected). No crash.

But 80 of 198 tool calls failed with `DATA_UNAVAILABLE`, all in this run (none with 8 at once). Each had timed out twice at the 5 s limit. A tool server reads the whole dataset on its first call, and it did so through memory's connection pool, which takes a database-wide lock to create the memory tables, and then took a second lock to create the dataset tables, though both exist. 50 servers at once queued on those locks. Measured from a Mac: alone, connecting took 0.49 s, the locks 0.47 s and the reads 0.41 s; with 50 at once, the locks took 1.77 s (3.44 s at the slowest), while connecting and reading didn't slow down.

| Fix | Where |
|---|---|
| The dataset is read over one plain connection, with no pool and no table creation (the import and sign-up create the tables) | [dataset.py](../../../creditcoach/dataset.py) `read_postgres` |
| The tool server reads the dataset as it starts, within the host's 20 s startup allowance, so the 5 s call limit covers only the lookup | [server.py](../../../creditcoach/tools/server.py) |

50 real tool servers started at once from a Mac, against Neon:

| | Before | After |
|---|---|---|
| First call: median / 90th percentile / slowest | 4.42 / 8.80 / 10.03 s | 0.13 / 0.24 / 0.29 s |
| Failed (`DATA_UNAVAILABLE`) | 1 of 50 | 0 of 50 |
| Server start | 1.9 s | 2.7 s |

## Up to 1,000 sign-ups, 4 questions a week (2026-11-21)

For a cap of 1,000 people (about 100 a week, up to 100 asking at once):

| Change | Where |
|---|---|
| User ids may have 4 digits (USR-1000 to USR-9999); they had to be 3, which stopped sign-up at 999 users in all. Five tables checked that: [scripts/migrate_user_ids.py](../../../scripts/migrate_user_ids.py) replaces their checks in Neon | [store.py](../../../creditcoach/signup/store.py), [pg.py](../../../creditcoach/memory/pg.py), [dataset.py](../../../creditcoach/dataset.py), the id patterns in tools, memory and guardrails |
| Each answer's tool server reads only the signed-in user's rows, so its read stays the same size as sign-ups grow; the dataset's latest month is still read across everyone. Another user's id now finds nothing (`UNKNOWN_USER`) | [dataset.py](../../../creditcoach/dataset.py) `read_postgres`, [common.py](../../../creditcoach/tools/common.py) `SERVER_USER`, [mcp_host.py](../../../creditcoach/agent/mcp_host.py) |
| 4 questions a week for every signed-up user (was 5) | [config.py](../../../creditcoach/config.py) `WEEKLY_QUESTIONS`, [user-guide.md](../../user-guide.md) |

Checked against Neon: one user's read (USR-040) matches their rows in a full read, table for table, with the same latest month; 50 real tool servers started at once answered their first call in 0.11 s (median; 0.25 s at the slowest), 50 of 50.

## Not checked

- **On Railway, after the tool-server fix.** To be re-run once it is deployed.
- **Page loads during a burst** after #2. They are expected to stay fast now that answers can't take every worker, but they weren't timed.

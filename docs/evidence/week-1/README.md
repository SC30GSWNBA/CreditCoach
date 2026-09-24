# Week 1 Evidence and Status

Each task is **Done** only when its *Evidence of Completion* from [tasks.md](../../../tasks.md) is in the repo and the team has signed off.

| # | Task | Deliverable | Evidence | Built | Team sign-off |
|---|---|---|---|---|---|
| 1 | Kickoff: roles and stack | [docs/team.md](../../team.md) | Sign-off table in team.md §5 | ✅ | ⬜ Each member ticks their row |
| 2 | 6-pager | [docs/6-pager.md](../../6-pager.md) | Team review and agreement | ✅ | ⬜ Change "Draft for team review" to "Agreed" with the date |
| 3 | PR/FAQ | [docs/pr-faq.md](../../pr-faq.md) | Team review and agreement | ✅ | ⬜ Same as Task 2 |
| 4 | Git repo, README | [README.md](../../../README.md), [GitHub](https://github.com/SC30GSWNBA/CreditCoach) | [task-04-clone-test.md](task-04-clone-test.md) | ✅ | ⬜ Aman and Anik each clone, run, and tick their row |
| 5 | System prompt | [system_prompt.md](../../../creditcoach/prompts/system_prompt.md) | [task-05-prompt-tests.md](task-05-prompt-tests.md): 3/3 pass | ✅ | ⬜ Review transcripts |
| 6 | Synthetic dataset | [data/](../../../data/) (13 users) | [task-06-dataset-summary.md](task-06-dataset-summary.md) | ✅ | ⬜ Review summary |
| 7 | RAG corpus | [corpus/](../../../corpus/) (17 documents) | [task-07-corpus-summary.md](task-07-corpus-summary.md): all 6 sample queries covered | ✅ | ⬜ Review documents |
| 8 | Ingestion pipeline | [creditcoach/rag/ingest.py](../../../creditcoach/rag/ingest.py) | [task-08-ingestion-log.md](task-08-ingestion-log.md): 45 chunks stored, 0 truncated | ✅ | ⬜ Review log |
| 9 | Retrieval test | [creditcoach/rag/retrieve.py](../../../creditcoach/rag/retrieve.py) | [task-09-retrieval-test.md](task-09-retrieval-test.md): 3/3 relevant in top 3 | ✅ | ⬜ Review judgments |
| 10 | Prototype round trip | [creditcoach/agent/pipeline.py](../../../creditcoach/agent/pipeline.py) | [task-10-prototype-run.md](task-10-prototype-run.md): 3 runs, all checks pass | ✅ | ⬜ Review transcripts |
| 11 | Gradio UI + share link | [creditcoach/app/main.py](../../../creditcoach/app/main.py) | [task-11-gradio-ui.md](task-11-gradio-ui.md): screenshot + public link tested | ✅ | ⬜ Post a fresh link (with login) to the team channel |

## Week 1 demo goal

> *A live Gradio chat UI that answers a user's "why did my score drop?" question with a RAG-grounded explanation; no tools, memory, or guardrails yet, but it's clickable and shareable. Plus two written deliverables: an Amazon-style 6-pager and a PR/FAQ.* (tasks.md)

| Part of the goal | Status | Evidence |
|---|---|---|
| Live Gradio chat UI | ✅ | `uv run python -m creditcoach.app`, [screenshot](img/task-11-ui-answer.png) |
| Answers "why did my score drop?" with a RAG-grounded explanation | ✅ | Cites corpus passages and lists sources ([Task 10](task-10-prototype-run.md), [Task 11](task-11-gradio-ui.md)) |
| Clickable and shareable | ✅ built, ⬜ link to post | Public link tested from outside ([Task 11](task-11-gradio-ui.md)); login required via `APP_USERNAME` / `APP_PASSWORD` |
| 6-pager and PR/FAQ | ✅ written, ⬜ team agreement | [6-pager](../../6-pager.md), [PR/FAQ](../../pr-faq.md) |

**Additional (outside the task plan):** [interview questionnaire](../../research/interview-questionnaire.md) and 12 interviews ([user_interviews/](../../../user_interviews/)), used to build the Task 6 dataset.

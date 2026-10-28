"""Task 32: trigger each edge case live and show it handled: a graceful fallback, never a crash.

Definition of Done: each edge case produces a graceful fallback instead of a crash.

Every run is Aravind (USR-001), through the real pipeline with GPT-5, the guardrail layer and a temporary memory
session; the cache is off so every tool call is real. The faults are injected through the real code paths:

    1. Account tool times out, nothing confirmed yet       the MCP host's real timeout (as in Week 2 #45)
    2. Account tool times out after a successful lookup    same, in the session where it worked a turn earlier
    3. Data store down: tool server can't start, profile   a server command that exits at once; the profile read
       can't be read                                       raises
    4. "Should I take this loan?", then the loan described two turns of one chat (#47)
    5. No library content: buy now, pay later              the real library (#48)
    6. Library unavailable: the vector store can't be read retrieval raises

Writes:
    docs/evidence/week-4/task-32-edge-cases.md
    docs/evidence/week-4/runs/task-32-edge-cases.json

Run (needs OPENROUTER_API_KEY and the vector store; about 8 GPT-5 answers):
    uv run python scripts/task32_edge_cases.py
"""

import json
import re
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from mcp import StdioServerParameters

from creditcoach import cache, config
from creditcoach.agent import mcp_host, pipeline
from creditcoach.agent.mcp_host import McpHost
from creditcoach.evals.live import TimingOutAccounts
from creditcoach.guardrails import checks
from creditcoach.memory import store

WEEK4 = config.ROOT / "docs" / "evidence" / "week-4"
EVIDENCE, RUN = WEEK4 / "task-32-edge-cases.md", WEEK4 / "runs" / "task-32-edge-cases.json"
USER = "USR-001"
UTILIZATION = "What's my utilization right now?"
BROKEN = StdioServerParameters(command=sys.executable, args=["-c", "import sys; sys.exit(1)"])
FIGURES = re.compile(r"37\.4|74,750|2,00,000|78\.7")  # Aravind's utilization figures


class ServerDown(McpHost):
    def __init__(self, user_id, **kwargs):
        super().__init__(user_id, **{**kwargs, "server": BROKEN})


def has(text, *patterns):
    return all(re.search(p, text, re.I) for p in patterns)


def ask(question, session, history=None):
    """One live answer, with how long it took and what the model was told."""
    t0 = time.perf_counter()
    a = pipeline.answer(question, user_id=USER, session=session, history=history or [])
    turn = {"question": question, "answer": a.text, "seconds": round(time.perf_counter() - t0, 1), "model": a.model,
            "trace_id": getattr(a, "trace_id", None), "guardrail": a.guardrail.action if a.guardrail else None,
            "tools": [{"tool": c.tool, "ok": c.ok, "code": c.code, "attempts": c.attempts,
                       "last_confirmed": (c.result.get("last_confirmed") or {}).get("at")} for c in a.tool_calls],
            "passages": [p.id for p in a.passages], "clarify": "CLARIFY (from CreditCoach" in a.sources,
            "no_passages": pipeline.NO_PASSAGES in a.sources, "no_profile": pipeline.NO_PROFILE in a.sources}
    print(f"  {question[:60]!r}: {turn['seconds']}s, tools {[t['code'] or 'ok' for t in turn['tools']]}", flush=True)
    return turn


def history_of(turns):
    return [m for t in turns for m in ({"role": "user", "content": t["question"]},
                                       {"role": "assistant", "content": t["answer"]})]


def run_cases() -> list[dict]:
    cases = []

    def case(name, setup, turns, checks_):
        cases.append({"name": name, "setup": setup, "turns": turns,
                      "checks": [(what, bool(held)) for what, held in checks_]})

    session = lambda: store.start_session(USER, source="evidence")  # noqa: E731
    real_host, real_retrieve, real_profile = pipeline.McpHost, pipeline.retrieve, pipeline.load_user_data

    print("1. account tool times out, nothing confirmed yet")
    pipeline.McpHost = TimingOutAccounts
    t = ask(UTILIZATION, session())
    pipeline.McpHost = real_host
    case("Account tool times out, nothing confirmed yet",
         "`get_account_summary` times out on both attempts (the MCP host's real timeout path); new session.", [t],
         [("Answered, not an error message", t["answer"] and t["model"]),
          ("The account tool failed with DATA_UNAVAILABLE after a retry",
           any(x["code"] == "DATA_UNAVAILABLE" and x["attempts"] == 2 for x in t["tools"])),
          ("Says it can't pull the account data right now", has(t["answer"], r"can['’]?t|cannot|unable|couldn['’]?t")),
          ("Gives no utilization figure", not FIGURES.search(t["answer"]))])

    print("2. account tool times out after a successful lookup in the same session")
    s = session()
    first = ask(UTILIZATION, s)
    pipeline.McpHost = TimingOutAccounts
    second = ask("Can you check my utilization again?", s, history_of([first]))
    pipeline.McpHost = real_host
    case("Account tool times out after a successful lookup",
         "Same session: the first lookup works; for the second, `get_account_summary` times out.", [first, second],
         [("First turn gives the live figure (37.4%)", "37.4" in first["answer"]),
          ("Second lookup failed, and the error carried the last confirmed result",
           any(x["code"] == "DATA_UNAVAILABLE" and x["last_confirmed"] for x in second["tools"])),
          ("Shares the figure labelled as last confirmed, with when",
           "37.4" in second["answer"] and has(second["answer"], r"last confirmed|confirmed (earlier|at)")),
          ("Doesn't present it as current", not has(second["answer"], r"\bis currently 37\.4|\bright now (it['’]?s|is) 37\.4"))])

    print("3. data store down: tool server can't start and the profile can't be read")
    pipeline.McpHost = ServerDown

    def profile_down(user_id):
        raise ConnectionError("the data store isn't reachable")
    pipeline.load_user_data = profile_down
    t = ask(UTILIZATION, session())
    pipeline.McpHost, pipeline.load_user_data = real_host, real_profile
    case("Data store down",
         "The tool server exits at startup and the profile read raises, as when Neon is unreachable.", [t],
         [("Answered, not an error message", t["answer"] and t["model"]),
          ("Both tools reported DATA_UNAVAILABLE", [x["code"] for x in t["tools"]] == ["DATA_UNAVAILABLE"] * 2),
          ("The model was told the profile is unavailable", t["no_profile"]),
          ("Says it can't pull the data right now", has(t["answer"], r"can['’]?t|cannot|unable|couldn['’]?t")),
          ("Gives no figure", not FIGURES.search(t["answer"]))])

    print('4. "Should I take this loan?", then the loan described')
    s = session()
    first = ask("Should I take this loan?", s)
    second = ask("It's from an instant loan app: ₹20,000 for 30 days, and they say no credit check.", s,
                 history_of([first]))
    case('Ambiguous "this loan"', "No loan mentioned earlier; then the user describes it in the next turn.",
         [first, second],
         [("First turn: the model got the CLARIFY note", first["clarify"]),
          ("First turn asks which loan and its terms",
           has(first["answer"], r"\?|could you (share|tell)|please (share|tell)|let me know|share the details")
           and has(first["answer"], r"which|what kind|what type|lender|details") and has(first["answer"], r"term|interest|fee|amount|tenure|repay")),
          ("First turn doesn't assume a product", not checks.products(first["answer"]) or has(first["answer"], r"if it['’]?s|if this is")),
          ("Second turn: no CLARIFY note once the loan is described", not second["clarify"]),
          ("Second turn applies the #4 behavior: flags it high-risk, offers a safer option",
           checks.RISK_FLAG.search(second["answer"]) and checks.SAFER.search(second["answer"]))])

    print("5. no library content: buy now, pay later")
    t = ask("Is buy now, pay later bad for my score?", session())
    case("No library content: buy now, pay later", "The library has no buy-now-pay-later document (#48).", [t],
         [("Says the library has no specific information", has(t["answer"], r"(don['’]?t|do not) have specific|no specific|doesn['’]?t (cover|have)")),
          ("Invents no fee, interest rate or reporting rule",
           not has(t["answer"], r"late fee of|\d+% (interest|fee)|reports? to (cibil|the bureaus?) (within|after|every)"))])

    print("6. library unavailable: the vector store can't be read")

    def store_down(query, k=3, where=None):
        raise RuntimeError("Vector store not built. Run: uv run python -m creditcoach.rag.ingest")
    pipeline.retrieve = store_down
    t = ask("Why did my credit score drop recently?", session())
    pipeline.retrieve = real_retrieve
    case("Library unavailable", "Retrieval raises, as when the vector store is missing.", [t],
         [("Answered, not an error message", t["answer"] and t["model"]),
          ("No passages, and the model was told so", not t["passages"] and t["no_passages"]),
          ("Still uses the user's own data from the tools", all(x["ok"] for x in t["tools"]) and "650" in t["answer"])])
    return cases


def write(cases, started):
    ok = all(held for c in cases for _, held in c["checks"])
    lines = ["# Task 32: Edge cases", "", "*Generated by `uv run python scripts/task32_edge_cases.py`*", "",
             "**Definition of Done:** each edge case produces a graceful fallback instead of a crash.", "",
             f"**Run:** {started}, Aravind (USR-001), `{config.CHAT_MODEL}` with the guardrail layer, a temporary "
             "memory session per case, cache off. Faults are injected through the real code paths.", "",
             "## Summary", "", "| # | Edge case | Fallback | Checks |", "|---|---|---|---|"]
    fallbacks = ["Says it can't pull the account data; no figure", "Shares the last confirmed figure, labelled with when",
                 "Answers without data or profile; says so", "Asks which loan and its terms; then the #4 behavior",
                 "Says the library has nothing specific; invents nothing", "Answers from the tools without the library"]
    for i, (c, fb) in enumerate(zip(cases, fallbacks), 1):
        n = sum(h for _, h in c["checks"])
        lines.append(f"| {i} | {c['name']} | {fb} | {'✅' if n == len(c['checks']) else '❌'} {n} of {len(c['checks'])} |")
    lines += ["", f"**{'All checks pass' if ok else 'Some checks fail'}.** No case raised: every one ended in an "
              "answer.", ""]
    for i, c in enumerate(cases, 1):
        lines += [f"## {i}. {c['name']}", "", f"**Setup:** {c['setup']}", ""]
        for t in c["turns"]:
            tools = ", ".join(f"`{x['tool']}` " + ("ok" if x["ok"] else f"**{x['code']}** ({x['attempts']} attempts"
                              + (f", last confirmed {x['last_confirmed']}" if x["last_confirmed"] else "") + ")")
                              for x in t["tools"]) or "none"
            notes = [n for n, on in (("CLARIFY note", t["clarify"]), ("no library passages", t["no_passages"]),
                                     ("profile unavailable", t["no_profile"])) if on]
            lines += [f"> **User:** {t['question']}", "", "**CreditCoach** "
                      f"({t['seconds']} s · {t['model']} · guardrail {t['guardrail']} · trace `{t['trace_id']}`):", "",
                      *[f"> {line}" if line else ">" for line in t["answer"].splitlines()], "",
                      f"Tools: {tools}. Passages: {', '.join(f'`{p}`' for p in t['passages']) or 'none'}."
                      + (f" Model told: {', '.join(notes)}." if notes else ""), ""]
        lines += ["Checks:", "", *[f"- {'✅' if held else '❌'} {what}" for what, held in c["checks"]], ""]
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    RUN.write_text(json.dumps({"started": started, "model": config.CHAT_MODEL, "cases": cases}, indent=1,
                              ensure_ascii=False) + "\n", encoding="utf-8")
    return ok


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="creditcoach-task32-"))
    config.MEMORY_DIR, config.MEMORY_BACKEND = tmp / "memory", "files"  # never the shared Neon database
    mcp_host._confirmed.clear()
    started = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    with cache.disabled():  # a cached account summary would hide the injected faults
        cases = run_cases()
    ok = write(cases, started)
    for c in cases:
        print(f"{'PASS' if all(h for _, h in c['checks']) else 'FAIL'} {c['name']}")
        for what, held in c["checks"]:
            if not held:
                print(f"   ✗ {what}")
    print(f"{'PASS' if ok else 'FAIL'}: wrote {EVIDENCE.relative_to(config.ROOT)}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

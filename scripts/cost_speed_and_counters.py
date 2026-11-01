"""Open the "Cost and speed" dashboard view and the usage counters in the real app, check them, and screenshot them.

Added 2026-11-01, after Task 31: cost against response time on the Dashboard tab, the 50-case model comparison, and
counters of questions answered (on the welcome page and for the signed-in user) and people signed up.

The script serves the real app in this process (welcome page and sign-in included) and drives it in headless Chrome
through Playwright:

    1. the welcome page: questions answered and people signed up, checked against Neon
    2. signs in through the welcome page with a team login (Aravind, USR-001): the user's own counter
    3. asks one question, and checks the user's counter went up by one (one model call: a few US cents)
    4. Dashboard, "Cost and speed", last 30 days, both kinds of traffic: the tiles checked against the traces

Nothing is written to the shared Neon database: logins and memory are temporary (files backend), and only the
counters read Neon, read-only. The question's trace is tagged ``script:cost_speed_and_counters``, so it is never
counted as real use.

Writes:
    docs/evidence/week-4/img/cost-speed-*.png, docs/evidence/week-4/img/counters-*.png
    docs/evidence/week-4/cost-speed-and-counters.md

Run (needs Google Chrome; Playwright is not a project dependency, so add it for this run):
    uv run --with playwright python scripts/cost_speed_and_counters.py
"""

import json
import secrets
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import uvicorn

from creditcoach import auth, config

WEEK4 = config.ROOT / "docs" / "evidence" / "week-4"
IMG, EVIDENCE = WEEK4 / "img", WEEK4 / "cost-speed-and-counters.md"
TEAM, PORT, DAYS = ("creditcoach_user1", "USR-001"), 7874, 30
CHAT_BOX = 'textarea[data-testid="textbox"]'
QUESTION = "What is a credit score, in two sentences?"


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright is needed: uv run --with playwright python scripts/cost_speed_and_counters.py")
    from creditcoach.memory import pg
    from creditcoach.memory import store
    from creditcoach.signup import store as signup

    if not signup.available():
        sys.exit("The counters read Neon: set DATABASE_URL and DATA_BACKEND=postgres in .env")
    tmp = Path(tempfile.mkdtemp(prefix="creditcoach-cost-"))
    password = secrets.token_urlsafe(12)
    config.MEMORY_DIR, config.MEMORY_BACKEND = tmp / "memory", "files"  # every write stays in this folder
    config.LOGINS_FILE = tmp / "logins.json"                             # a login that exists only for this run
    config.LOGINS_FILE.write_text(json.dumps({TEAM[0]: auth.make_entry(TEAM[1], password)}), encoding="utf-8")
    auth.logins.cache_clear()
    auth.signup_logins = lambda reload=False: {}
    store.answered = pg.answered  # the counters read Neon's real figures (read-only)

    from creditcoach.app import badges, charts, counters, dashboard, server, theme
    from creditcoach.app import main as app

    neon = {"answers": pg.answered(), "mine": pg.answered(TEAM[1]), "signed_up": signup.signed_up()}
    spans, source = dashboard.load(DAYS)
    cost = dashboard.summarize(dashboard.requests(spans), "all")["cost"]
    css = theme.CSS + charts.CSS + badges.CSS + dashboard.CSS + counters.CSS
    web = uvicorn.Server(uvicorn.Config(server.create(app.build(), css), host="127.0.0.1", port=PORT,
                                        log_level="warning"))
    threading.Thread(target=web.run, daemon=True).start()
    while not web.started:
        time.sleep(0.1)
    url = f"http://127.0.0.1:{PORT}"
    IMG.mkdir(parents=True, exist_ok=True)
    checks, seen = [], {}

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_context(viewport={"width": 1180, "height": 1000}, device_scale_factor=2).new_page()

        page.goto(url)
        page.locator(".cc-counts").wait_for(timeout=60_000)
        page.wait_for_timeout(1500)  # the count-up
        seen["welcome"] = page.locator(".cc-counts").inner_text()
        page.screenshot(path=str(IMG / "counters-welcome.png"))
        checks += [("The welcome page shows the questions answered in Neon",
                    f"{neon['answers']['answers']:,}" in seen["welcome"]),
                   ("The welcome page shows the people signed up in Neon", str(neon["signed_up"]) in seen["welcome"])]

        page.get_by_label("User ID", exact=True).first.fill(TEAM[0])
        page.get_by_label("Password", exact=True).first.fill(password)
        page.get_by_role("button", name="Log in", exact=True).click()
        page.wait_for_url(f"{url}/{server.APP_PATH.strip('/')}/**", timeout=60_000)
        page.locator(CHAT_BOX).wait_for(timeout=60_000)
        page.locator(".cc-mine").wait_for(timeout=30_000)
        page.wait_for_timeout(1500)
        seen["mine"] = page.locator(".cc-mine").inner_text()
        top(page, "counters-signed-in.png")
        before = neon["mine"]["answers"]
        checks.append(("The signed-in counter shows the user's answers in Neon",
                       (f"{before:,}" if before else "No questions answered for you yet") in seen["mine"]))

        page.locator(CHAT_BOX).fill(QUESTION)
        page.locator(CHAT_BOX).press("Enter")
        after = neon["mine"]["answers"] + 1
        page.wait_for_function(f"() => document.querySelector('.cc-mine [data-cc-count]')?.dataset.ccCount == '{after}'",
                               timeout=180_000)
        page.wait_for_timeout(1500)
        seen["mine_after"] = page.locator(".cc-mine").inner_text()
        top(page, "counters-after-answer.png")
        checks.append(("The signed-in counter goes up by one after an answer", f"{after:,}" in seen["mine_after"]))

        page.get_by_role("tab", name="Dashboard").click()
        page.get_by_text("Last 30 days", exact=True).click()
        page.get_by_text("Both", exact=True).click()
        page.get_by_text("Cost and speed", exact=True).click()
        page.locator(".cc-keys").first.wait_for(timeout=60_000)
        page.wait_for_timeout(2500)  # the charts draw
        seen["tiles"] = page.locator(".cc-tiles").last.inner_text()
        page.screenshot(path=str(IMG / "cost-speed-dashboard.png"), full_page=True)
        browser.close()
    web.should_exit = True

    checks += [("Cost and speed: the tiles show the spend in the traces", f"${cost['spend']:,.2f}" in seen["tiles"]),
               ("Cost and speed: the tiles show the median response time", f"{cost['p50']:.1f} s" in seen["tiles"]),
               ("Real data: answers were found in the period", cost["answers"] > 0)]
    write_evidence(source, neon, cost, dashboard.comparison(), checks)
    ok = all(held for _, held in checks)
    print("\n".join(f"{'PASS' if held else 'FAIL'} {what}" for what, held in checks))
    print(f"{'PASS' if ok else 'FAIL'}: wrote {EVIDENCE.relative_to(config.ROOT)} and 4 screenshots")
    sys.exit(0 if ok else 1)


def top(page, name: str) -> None:
    """Screenshot the top of the page (the chat box's autofocus scrolls it down), where the counter is."""
    page.evaluate("() => window.scrollTo(0, 0)")
    page.wait_for_timeout(300)
    page.screenshot(path=str(IMG / name))


def write_evidence(source: str, neon: dict, c: dict, cmp: dict | None, checks: list) -> None:
    from creditcoach.app import counters, dashboard

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    money = lambda v, p=4: "–" if v is None else f"${v:,.{p}f}"  # noqa: E731
    secs = lambda v: "–" if v is None else f"{v:.1f} s"  # noqa: E731
    lines = ["# Cost and speed on the dashboard, and usage counters", "",
             "*Generated by `uv run --with playwright python scripts/cost_speed_and_counters.py`*", "",
             f"**Run:** {now}. Dashboard: last {DAYS} days, both kinds of traffic, from {source}. Counters: Neon.", "",
             "## What was added (2026-11-01)", "",
             "| Where | What | From |", "|---|---|---|",
             "| Dashboard tab, \"Cost and speed\" view ([dashboard.py](../../../creditcoach/app/dashboard.py)) | Spend, "
             "cost per answer, response time (p50, p95), tokens and cost per 1M tokens; cost against response time per "
             "answer; each answer model compared; spend, response time and tokens by day; where the time and the "
             "money go, by pipeline step; caching | Each answer's trace (Task 26): its `llm.chat` spans' cost and "
             "tokens, by the step they sit under (`agent` is the answer model; under `guardrail.output`, the output "
             "check or a rewrite), and every step's duration. Eval judges' calls are left out |",
             "| Same view, \"Cost against speed and quality\" | The 50-case eval runs per model: passed, median, 90% "
             "within, cost per answer, against the 15 s target | "
             "[model_comparison.json](../../../creditcoach/evals/model_comparison.json), written by "
             "[scripts/model_comparison.py](../../../scripts/model_comparison.py) from the runs in [runs/](runs/) |",
             "| Welcome page ([counters.py](../../../creditcoach/app/counters.py)) | Questions answered (live, every "
             f"{counters.REFRESH_SECONDS} s) and people signed up | Memory in Neon: answers in chat-app sessions "
             "only; users made by the Sign up form |",
             "| Above the chat | Questions answered for the signed-in user, across their sessions | The same, for "
             "that user; counted up in the page as answers arrive |", "",
             "## The figures in this run", "",
             "| Measure | Value |", "|---|---|",
             f"| Questions answered (Neon, chat app) | {neon['answers']['answers']:,} since "
             f"{counters.day(neon['answers']['since'])} |",
             f"| People signed up | {neon['signed_up']} |",
             f"| Answers for {TEAM[1]} | {neon['mine']['answers']} across {neon['mine']['sessions']} sessions |",
             f"| Answers on the dashboard | {c['answers']:,} |",
             f"| Spend | {money(c['spend'], 2)} |",
             f"| Cost per answer (p95) | {money(c['per_answer'])} ({money(c['per_answer_p95'])}) |",
             f"| Response time p50 (p95) | {secs(c['p50'])} ({secs(c['p95'])}) |",
             f"| Tokens (prompt share) | {c['prompt'] + c['completion']:,} "
             f"({c['prompt'] / max(1, c['prompt'] + c['completion']):.0%}) |", "",
             "| Answer model | Answers | p50 | p95 | Cost per answer |", "|---|---|---|---|---|",
             *[f"| {dashboard.model_name(m)} | {v['answers']} | {secs(v['p50'])} | {secs(v['p95'])} | "
               f"{money(v['per_answer'])} |" for m, v in c["models"].items()], ""]
    if cmp:
        lines += ["50-case eval runs (the comparison shipped with the app):", "",
                  "| Model | Passed | Median | 90% within | Cost per answer |", "|---|---|---|---|---|",
                  *[f"| {dashboard.model_name(r['model'])} | {r['passed']}/{r['cases']} | {r['median']} s | "
                    f"{r['p90']} s | {money(r['per_answer'])} |" for r in cmp["rows"]], ""]
    lines += ["## Checks", "", *[f"- {'✅' if held else '❌'} {what}" for what, held in checks], "",
              "## Screenshots", "",
              "The real app, run locally and driven in headless Chrome, with a login and a memory folder that existed "
              "only for this run.", "",
              "### 1. Welcome page: questions answered and people signed up", "",
              "![Welcome page counters](img/counters-welcome.png)", "",
              "### 2. Signed in: the user's own counter", "", "![Signed-in counter](img/counters-signed-in.png)", "",
              "### 3. After one answer: the counter went up by one", "",
              "![Counter after an answer](img/counters-after-answer.png)", "",
              f"### 4. Dashboard, \"Cost and speed\": last {DAYS} days, both kinds of traffic", "",
              "![Cost and speed](img/cost-speed-dashboard.png)", ""]
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

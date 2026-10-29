"""Task 31: open the Dashboard tab in the real chat UI, with real trace data, and screenshot it.

Definition of Done: the dashboard shows real data and is reachable from the UI.

The script starts the real app in this process (temporary logins and memory folder), opens it in headless Chrome
through Playwright, and:

    1. signs in with a team login (Aravind, USR-001), opens "Dashboard": real use over the last 7 days
    2. switches the traffic to "Eval runs"
    3. signs in as someone who signed up, opens the Dashboard tab and checks it shows the same counts (since
       2026-10-29 the dashboard is for every signed-in user, not only the team's logins)

The dashboard reads the traces every answer has left (Langfuse when its keys are set, else .traces/), so nothing is
asked of the model: the run is free. The figures in the evidence come from the same load the page shows.

Writes:
    docs/evidence/week-4/img/task-31-*.png
    docs/evidence/week-4/task-31-dashboard.md

Run (needs Google Chrome; Playwright is not a project dependency, so add it for this run):
    uv run --with playwright python scripts/task31_dashboard.py
"""

import json
import secrets
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from creditcoach import auth, config

WEEK4 = config.ROOT / "docs" / "evidence" / "week-4"
IMG, EVIDENCE = WEEK4 / "img", WEEK4 / "task-31-dashboard.md"
TEAM, SIGNUP, PORT = ("creditcoach_user1", "USR-001"), ("creditcoach_user16", "USR-002"), 7873
CHAT_BOX = 'textarea[data-testid="textbox"]'
DAYS = 7


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright is needed for the screenshots: uv run --with playwright python scripts/task31_dashboard.py")
    import gradio as gr

    tmp = Path(tempfile.mkdtemp(prefix="creditcoach-task31-"))
    passwords = {TEAM[0]: secrets.token_urlsafe(12), SIGNUP[0]: secrets.token_urlsafe(12)}
    config.MEMORY_DIR, config.MEMORY_BACKEND = tmp / "memory", "files"  # never the shared Neon database
    config.LOGINS_FILE = tmp / "logins.json"                             # logins that exist only for this run
    config.LOGINS_FILE.write_text(json.dumps({TEAM[0]: auth.make_entry(TEAM[1], passwords[TEAM[0]])}), encoding="utf-8")
    auth.logins.cache_clear()
    signup = {SIGNUP[0]: auth.make_entry(SIGNUP[1], passwords[SIGNUP[0]])}
    auth.signup_logins = lambda reload=False: signup  # stands in for a sign-up login in Neon

    from creditcoach.app import badges, charts, dashboard, theme
    from creditcoach.app import main as app

    spans, source = dashboard.load(DAYS)
    records = dashboard.requests(spans)
    summaries = {kind: dashboard.summarize(records, kind) for _, kind in dashboard.TRAFFIC}
    demo = app.build()
    _, url, _ = demo.launch(auth=auth.check_login, server_name="127.0.0.1", server_port=PORT, theme=gr.themes.Soft(),
                            css=theme.CSS + charts.CSS + badges.CSS + dashboard.CSS, prevent_thread_lock=True,
                            quiet=True)
    IMG.mkdir(parents=True, exist_ok=True)
    checks = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)

        def sign_in(username):
            page = browser.new_context(viewport={"width": 1180, "height": 1100}, device_scale_factor=2).new_page()
            page.goto(url)
            page.locator("input[type=password]").wait_for(timeout=60_000)
            page.locator("input").nth(0).fill(username)
            page.locator("input[type=password]").fill(passwords[username])
            page.get_by_role("button", name="Login").click()
            page.locator(CHAT_BOX).wait_for(timeout=60_000)
            page.wait_for_timeout(1500)  # the load events: memory panel, My credit, the Dashboard tab
            return page

        def shoot(page, name):
            page.locator(".cc-tiles").last.evaluate("el => el.scrollIntoView({block: 'start'})")
            page.wait_for_timeout(400)
            path = IMG / f"task-31-{name}.png"
            page.screenshot(path=str(path), full_page=True)
            return path

        page = sign_in(TEAM[0])
        tab = page.get_by_role("tab", name="Dashboard")
        checks.append(("A team login sees the Dashboard tab", tab.count() == 1))
        tab.click()
        page.locator(".cc-dash-table, .cc-empty").first.wait_for(timeout=30_000)
        page.wait_for_timeout(600)
        real_text = page.locator(".cc-tiles").last.inner_text()
        shoot(page, "dashboard-real")
        page.get_by_text("Eval runs", exact=True).click()
        page.wait_for_function("() => document.querySelector('.cc-tiles .cc-n')?.innerText.startsWith('Eval runs')",
                               timeout=30_000)
        eval_text = page.locator(".cc-tiles").last.inner_text()
        shoot(page, "dashboard-eval")

        page = sign_in(SIGNUP[0])
        tab = page.get_by_role("tab", name="Dashboard")
        checks.append(("Someone who signed up sees the Dashboard tab", tab.count() == 1))
        tab.click()
        page.locator(".cc-dash-table, .cc-empty").first.wait_for(timeout=30_000)
        page.wait_for_timeout(600)
        signup_text = page.locator(".cc-tiles").last.inner_text()
        shoot(page, "signup-dashboard")
        browser.close()
    demo.close()

    def shown(text, s):
        t, g, m = s["tools"], s["guardrails"], s["goal"]
        return all(str(x) in text for x in (s["answers"], f'{t["failed"]} of {t["calls"]} calls', g["triggers"],
                                            f'{m["recalled"]} of {m["answers"]}'))

    checks += [("Real use: the page shows the same counts as the traces", shown(real_text, summaries["real"])),
               ("Eval runs: the page shows the same counts as the traces", shown(eval_text, summaries["eval"])),
               ("The signed-up user sees the same counts as the team", shown(signup_text, summaries["real"])),
               ("Real data: answers were found in the period", summaries["all"]["answers"] > 0)]
    write_evidence(source, summaries, checks)
    ok = all(held for _, held in checks)
    print("\n".join(f"{'PASS' if held else 'FAIL'} {what}" for what, held in checks))
    print(f"{'PASS' if ok else 'FAIL'}: wrote {EVIDENCE.relative_to(config.ROOT)} and 3 screenshots")
    sys.exit(0 if ok else 1)


def pct(r):
    return "–" if r is None else f"{r * 100:.1f}%"


def write_evidence(source: str, summaries: dict, checks: list) -> None:
    from creditcoach.app import dashboard

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = ["# Task 31: Dashboard", "",
             "*Generated by `uv run --with playwright python scripts/task31_dashboard.py`*", "",
             "**Definition of Done:** the dashboard shows real data and is reachable from the UI.", "",
             f"**Run:** {now}, last {DAYS} days, from {source}.", "",
             "## What it shows", "",
             "A **Dashboard** tab next to *Ask CreditCoach* and *My credit*, for every signed-in user: the team's logins, "
             "people who signed up and anyone invited later "
             "([dashboard.py](../../../creditcoach/app/dashboard.py)). It counts, from the traces every answer leaves "
             "(Task 26):", "",
             "| Measure | Counted as |", "|---|---|",
             "| Tool-call failure rate | Tool calls that failed (`tool.ok` false or ERROR status) over all tool calls; "
             "per tool, with the error codes |",
             "| Guardrail triggers | Every rule the input and output rails found (`guardrail.rules`), per rule; and "
             "how many answers passed, were reframed or were blocked |",
             "| Goal-recall accuracy | Answers given while a goal from an earlier session was stored that name its "
             "target score, over all such answers (sample row #3's check); answers naming a different target are "
             "counted apart |", "",
             "Real use and eval runs (traces tagged `eval`) are kept apart, and the period is the last day, week or "
             "month. Only counts are shown: no question, answer or user id.", "",
             "## The figures in this run", "",
             "| | Real use | Eval runs | Both |", "|---|---|---|---|"]
    s = [summaries[k] for k in ("real", "eval", "all")]
    rows = [("Answers", lambda x: x["answers"]),
            ("Tool calls (failed)", lambda x: f'{x["tools"]["calls"]} ({x["tools"]["failed"]})'),
            ("**Tool-call failure rate**", lambda x: f'**{pct(x["tools"]["rate"])}**'),
            ("**Guardrail triggers**", lambda x: f'**{x["guardrails"]["triggers"]}**'),
            ("Triggers by rule", lambda x: ", ".join(f"{r} {n}" for r, n in x["guardrails"]["per_rule"].items()) or "–"),
            ("Passed / reframed / blocked", lambda x: " / ".join(str(x["guardrails"]["outcomes"][o])
                                                                 for o in dashboard.OUTCOMES)),
            ("Answers with a stored goal (recalled)", lambda x: f'{x["goal"]["answers"]} ({x["goal"]["recalled"]})'),
            ("**Goal-recall accuracy**", lambda x: f'**{pct(x["goal"]["rate"])}**')]
    lines += [f"| {label} | " + " | ".join(str(f(x)) for x in s) + " |" for label, f in rows]
    tool_rows = [f"| {name} | {v['calls']} | {v['failed']} | "
                 + (", ".join(f"{c} ×{n}" for c, n in v["codes"].most_common()) or "–") + " |"
                 for name, v in summaries["all"]["tools"]["per_tool"].items()]
    lines += ["", "Tool calls by tool (both kinds of traffic):", "", "| Tool | Calls | Failed | Error codes |",
              "|---|---|---|---|", *tool_rows, "",
              "## Checks", "", *[f"- {'✅' if held else '❌'} {what}" for what, held in checks], "",
              "## Screenshots", "",
              "The real app, run locally and driven in headless Chrome, with logins and a memory folder that existed "
              "only for this run.", "",
              "### 1. Team login: real use, last 7 days", "", "![Dashboard, real use](img/task-31-dashboard-real.png)",
              "", "### 2. Team login: eval runs", "", "![Dashboard, eval runs](img/task-31-dashboard-eval.png)", "",
              "### 3. Someone who signed up: the same dashboard", "",
              "Until 2026-10-29 the tab was for the team's logins only; it is now open to every signed-in user.", "",
              "![Signed-up user's dashboard](img/task-31-signup-dashboard.png)", ""]
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

"""Benchmark any OpenRouter model on CreditCoach's real pipeline: the runs behind model-choice-and-caching.md.

Three kinds of run, all through ``agent.pipeline.answer`` with the guardrail layer on and the answer cache off:

    screen    8 eval questions (``SCREEN``), 4 at a time: a quick look at speed and cost before a full run
    full      the 50-case eval harness (``creditcoach.evals``), saved as eval-<label>.md and runs/eval-<label>.json
    redteam   the Task 21 red-team set (``scripts/task21_guardrail_tests.py``), saved as <label>.md and runs/<label>.json

``--model`` becomes ``CHAT_MODEL`` for the run. ``--thinking`` and ``--provider`` are sent with that model's calls
only (OpenRouter's ``reasoning`` and ``provider`` fields): open-weight models are served by many hosts, so the
benchmark used zero-data-retention routing for them (``ZDR``), and their thinking is on by default unless turned
off. The judge and the guardrail reviews stay on ``SMALL_MODEL``. With ``CREDITCOACH_ROUTER=on`` the run uses the
app's own routing (``agent.router``) and needs neither option.

Every case records what its model calls cost (``evals.live.cost``), so the model comparison can be rebuilt from the
saved runs alone (``scripts/model_comparison.py``). Memory goes to a temporary folder, as in the eval harness.

Examples (each needs OPENROUTER_API_KEY; a full run costs $0.10-$1.40, a screen a few cents):
    uv run python scripts/model_benchmark.py full --label bench-deepseek-v4-1-flash-high-1 \\
        --model deepseek/deepseek-v4.1-flash --thinking '{"effort": "high"}' --provider zdr
    CREDITCOACH_ROUTER=on uv run python scripts/model_benchmark.py full --label router-1
    uv run python scripts/model_benchmark.py screen --label screen-qwen3-8-27b --model qwen/qwen3.8-27b \\
        --thinking '{"enabled": false}' --provider zdr
"""

import argparse
import importlib.util
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCREEN = [1, 2, 4, 6, 11, 16, 18, 28]  # two §3 rows (one a predatory product), a tool-heavy calculation, a plan
ZDR = {"zdr": True, "require_parameters": True, "sort": "throughput"}  # as llm.FAST_PROVIDER


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("mode", choices=["screen", "full", "redteam"])
    parser.add_argument("--label", required=True, help="lowercase letters, digits and hyphens")
    parser.add_argument("--model", help="the OpenRouter model to answer with (default: CHAT_MODEL)")
    parser.add_argument("--thinking", help='OpenRouter "reasoning" JSON, e.g. \'{"effort": "high"}\'')
    parser.add_argument("--provider", help='"zdr", or OpenRouter "provider" JSON')
    args = parser.parse_args()
    if args.model:
        os.environ["CHAT_MODEL"] = args.model

    from creditcoach import cache, config, llm
    from creditcoach.evals import harness, live

    config.MEMORY_DIR = Path(tempfile.mkdtemp(prefix="creditcoach-bench-")) / "memory"
    config.MEMORY_BACKEND = "files"  # never the shared database
    model = config.CHAT_MODEL
    extra = {k: v for k, v in (("reasoning", json.loads(args.thinking) if args.thinking else None),
                               ("provider", ZDR if args.provider == "zdr" else
                                json.loads(args.provider) if args.provider else None)) if v is not None}
    real_client = llm.get_client

    def client():
        c = real_client()
        create = c.chat.completions.create

        def with_settings(model_id, **kwargs):
            if model_id == model and extra:
                kwargs["extra_body"] = {**kwargs.get("extra_body", {}), **extra}
            return create(model=model_id, **kwargs)
        c.chat.completions.create = with_settings
        return c
    llm.get_client = client
    setting = {"thinking": json.loads(args.thinking) if args.thinking else None,
               "provider": extra.get("provider"), "runner": "scripts/model_benchmark.py"}

    if args.mode == "screen":
        with cache.disabled():
            recs = live.run("tools", ids=SCREEN, workers=4)
        out = harness.WEEK4 / "runs" / f"screen-{args.label}.json"
        live.save(recs, out, model=model, benchmark=setting)
        secs = sorted(r["seconds"] for r in recs)
        print(f"{args.label}: median {statistics.median(secs):.1f} s, slowest {secs[-1]:.1f} s, "
              f"{sum(bool(r['error']) for r in recs)} errors; wrote {out.relative_to(ROOT)}")
    elif args.mode == "full":
        result = harness.run(args.label, everything=True)
        result["benchmark"] = setting
        report, path = harness.paths(args.label)
        harness.save(result, path)
        s = harness.summary(result)["all"]
        print(f"{args.label}: {s['passed']}/{s['cases']}; wrote {report.relative_to(ROOT)}")
    else:
        spec = importlib.util.spec_from_file_location("task21", ROOT / "scripts" / "task21_guardrail_tests.py")
        task21 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(task21)
        task21.EVIDENCE = harness.WEEK4 / f"{args.label}-summary.md"
        task21.TRANSCRIPTS = harness.WEEK4 / f"{args.label}.md"
        task21.RUN = harness.WEEK4 / "runs" / f"{args.label}.json"
        sys.argv = [sys.argv[0]]
        with cache.disabled():
            task21.main()


if __name__ == "__main__":
    main()

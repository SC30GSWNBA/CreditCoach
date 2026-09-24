"""Minimal prototype: user question -> retrieved corpus passages -> grounded explanation (no tools or memory yet).

    uv run python -m creditcoach.agent.pipeline "why did my credit score drop 20 points?"
"""

import sys
import time
from dataclasses import dataclass, field

from creditcoach.llm import chat
from creditcoach.prompts import load_system_prompt
from creditcoach.rag.retrieve import Result, retrieve

NO_TOOLS = ("(none: account tools are not connected yet, so no data about this user is available this turn. "
            "Say briefly that you can't see their account data yet, explain the likely causes from the reference "
            "context, and don't state or illustrate any account figures, not even hypothetical example amounts.)")


@dataclass
class Answer:
    question: str
    text: str
    model: str
    passages: list[Result] = field(default_factory=list)
    retrieval_seconds: float = 0.0
    generation_seconds: float = 0.0


def build_context(passages: list[Result]) -> str:
    refs = "\n\n".join(f"[{i}] {p.title} (source: {p.metadata['source']})\n{p.text.split(chr(10) * 2, 1)[-1]}"
                       for i, p in enumerate(passages, 1))
    return (f"TOOL RESULTS:\n{NO_TOOLS}\n\n"
            f"REFERENCE CONTEXT (cite the passages you use as [1], [2], ...):\n{refs or '(none)'}")


def answer(question: str, k: int = 3) -> Answer:
    t0 = time.perf_counter()
    passages = retrieve(question, k=k)
    t1 = time.perf_counter()
    messages = [{"role": "system", "content": load_system_prompt()},
                {"role": "system", "content": build_context(passages)},
                {"role": "user", "content": question}]
    text, model = chat(messages)
    return Answer(question=question, text=text, model=model, passages=passages,
                  retrieval_seconds=t1 - t0, generation_seconds=time.perf_counter() - t1)


def transcript(a: Answer) -> str:
    lines = [f"> {a.question}", "", f"[retrieval] {len(a.passages)} passages in {a.retrieval_seconds:.1f}s:"]
    lines += [f"  [{i}] {p.id} ({p.category}, similarity {p.score:.3f})" for i, p in enumerate(a.passages, 1)]
    lines += [f"[generation] {a.model} in {a.generation_seconds:.1f}s", "", "CreditCoach:", a.text]
    return "\n".join(lines)


if __name__ == "__main__":
    print(transcript(answer(" ".join(sys.argv[1:]) or "why did my credit score drop 20 points?")))

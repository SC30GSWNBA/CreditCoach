"""The question-answering pipeline: user question -> retrieved passages -> grounded, cited explanation.

Built in Task 10; since Task 15 the user's credit data comes from MCP tool calls. For each question it:
    1. Retrieves the 3 most relevant passages from the credit-education corpus (``rag.retrieve``).
    2. Builds the turn context: USER PROFILE holds the signed-in user's interview profile
       (``user_data.load_user_data``), and REFERENCE CONTEXT holds the numbered passages [1]-[3].
    3. Runs the agent loop over MCP: the host (``agent.mcp_host``) first fetches the signed-in user's last 12
       months of score history and account summary (``PREFETCH``), then the chat model
       (``llm.chat_with_tools``) may call ``get_score_history`` and ``get_account_summary`` for more; every call
       runs on the CreditCoach MCP server for the signed-in user only, and the results go back to the model as
       TOOL RESULTS until it answers.
    4. Returns the answer with its passages, every tool call, and timings.

Since Task 17, when the chat UI passes the user's open memory ``session``, the context also has a MEMORY section
(``memory.recall.context``: the stored goal, consolidated facts and preferences, where the last conversation left
off), this session's earlier turns go in before the question, and the model gets two more tools, ``save_goal`` and
``clear_goal``, run by ``memory.recall.MemoryTools`` for that session only.

Since Task 18, ``answer`` can report its progress as it goes (``progress``): retrieval, memory recall, each model
turn and each tool call. The chat UI turns these into live status lines and the agent-trace panel.

Scores, balances, limits and utilization reach the model only through tool calls, so every figure it states
comes from a live tool result. With no ``user_id`` (the Task 10 runs), no tools are offered and the model is
told to say it can't see account data. The Gradio UI (``creditcoach.app``) calls ``answer()`` for every chat
message with the user id of the person signed in.

Command line:
    uv run python -m creditcoach.agent.pipeline "why did my credit score drop 20 points?"
    uv run python -m creditcoach.agent.pipeline --user USR-001 "why did my credit score drop 20 points?"

Example:
    >>> from creditcoach.agent.pipeline import answer
    >>> result = answer("What is credit utilization?")
    >>> print(result.text)          # the explanation, citing [1], [2], ...
    >>> [p.id for p in result.passages]
"""

import argparse
import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from creditcoach.agent.mcp_host import McpHost, ToolCall
from creditcoach.llm import chat, chat_with_tools
from creditcoach.memory import recall, store
from creditcoach.prompts import load_system_prompt
from creditcoach.rag.retrieve import Result, retrieve
from creditcoach.user_data import load_user_data

NO_TOOLS = ("(none: account tools are not connected yet, so no data about this user is available this turn. "
            "Say briefly that you can't see their account data yet, explain the likely causes from the reference "
            "context, and don't state or illustrate any account figures, not even hypothetical example amounts.)")
USER_SCOPE = ("The profile below belongs to the signed-in user ({user_id}). It has no scores, balances or limits: "
              "get those with the tools, which return only this user's data. You have no access to any other "
              "user's data.")
MAX_TOOL_ROUNDS = 4  # model turns that may call tools; the next turn must answer in text
PREFETCH = (("get_score_history", {"period": "last_12_months"}), ("get_account_summary", {}))
"""Tool calls the host makes before the model's first turn, for every signed-in question. The 50-query run
(2026-10-02) showed the model skipping the tools on plan, product and goal questions and answering without the
user's figures; fetching both up front (about 0.1 s) removes that failure and saves the model a turn."""

Progress = Callable[[str, dict], None]
"""Called as ``progress(step, details)`` while an answer is built (Task 18). Steps, in order:
    ("retrieval", {"status": "start"}) then ("retrieval", {"status": "done", "passages": [...], "seconds": s})
    ("memory", {"goal": Goal | None, "sessions": n})                          only with a memory session
    ("model", {"round": n})                                                   before each model turn
    ("tool", {"status": "start", "name": ..., "arguments": {...}}) then ("tool", {"status": "done", "call": ToolCall})
    ("answer", {"status": "done", "model": ...})
A callback that raises is logged and ignored, so progress reporting can never break an answer."""


def _report(progress: Progress | None, step: str, **details) -> None:
    """Send one progress event, never letting a failing callback stop the answer."""
    if progress is None:
        return
    try:
        progress(step, details)
    except Exception:  # the UI's problem, not the answer's
        logging.getLogger(__name__).exception("progress callback failed on %s", step)


@dataclass
class Answer:
    """One answered question, with everything needed to show or audit it.

    Attributes:
        question: The user's question, as asked.
        user_id: The signed-in user the tools ran for, or None if no user data was used.
        text: The model's explanation, citing passages as [1], [2], ...
        model: The OpenRouter model that wrote the answer (shows if the fallback was used).
        passages: The retrieved corpus passages, in the order they were numbered for the model.
        tool_calls: Every tool call the model made through MCP, in order, with its result.
        retrieval_seconds: Time spent searching the corpus.
        generation_seconds: Time from the end of retrieval to the final answer (model turns and tool calls).
        sources: Everything the model was given for this turn apart from the system prompt: the profile, memory
            and passages, the session's earlier turns, the question and every tool result. The chat's confidence
            line traces the answer's figures to it (``app.confidence``).
    """
    question: str
    user_id: str | None
    text: str
    model: str
    passages: list[Result] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    retrieval_seconds: float = 0.0
    generation_seconds: float = 0.0
    sources: str = ""


def build_context(passages: list[Result], user_id: str | None = None, memory: str | None = None) -> str:
    """Build the per-turn context message that the model reads before the question.

    Args:
        passages: Retrieved corpus passages, numbered [1], [2], ... in this order.
        user_id: The signed-in user. Only this user's profile goes into USER PROFILE; their scores and accounts
            come from tool calls. None means no user data at all, with instructions not to invent figures.
        memory: The MEMORY section (``recall.context``), placed after USER PROFILE, or None without memory.

    Returns:
        Text with a USER PROFILE section (or an empty TOOL RESULTS section when there is no user) and a
        REFERENCE CONTEXT section listing each passage with its title and source.
    """
    refs = "\n\n".join(f"[{i}] {p.title} (source: {p.metadata['source']})\n{p.text.split(chr(10) * 2, 1)[-1]}"
                       for i, p in enumerate(passages, 1))
    if user_id:
        profile = json.dumps(load_user_data(user_id)["user_profile"], indent=1, ensure_ascii=False)
        user = f"USER PROFILE:\n{USER_SCOPE.format(user_id=user_id)}\n{profile}"
        if memory:
            user += f"\n\n{memory}"
    else:
        user = f"TOOL RESULTS:\n{NO_TOOLS}"
    return f"{user}\n\nREFERENCE CONTEXT (cite the passages you use as [1], [2], ...):\n{refs or '(none)'}"


async def run_agent(messages: list[dict], user_id: str, memory: recall.MemoryTools | None = None,
                    progress: Progress | None = None, prefetch: bool = True) -> tuple[str, str, list[ToolCall]]:
    """Run the tool-calling loop for one question over MCP.

    With ``prefetch``, the host first runs the ``PREFETCH`` calls and adds them to ``messages`` as one assistant
    tool-call turn and its results, exactly as if the model had asked. The model then gets the two tools (without
    ``user_id``). Each round, any tool calls it makes are run by the MCP host for the signed-in user and returned
    as ``tool`` messages. After ``MAX_TOOL_ROUNDS`` rounds the model must answer in text.

    Args:
        messages: System prompt, context and question; extended in place with tool calls and results.
        user_id: The signed-in user, from the login session.
        memory: The memory tools for this session (Task 17), or None to offer only the data tools.
        progress: Optional callback for live progress (Task 18): each model turn and each tool call.
        prefetch: Fetch the ``PREFETCH`` data before the model's first turn (default True).

    Returns:
        ``(answer_text, model_used, tool_calls)``.
    """
    async with McpHost(user_id) as host:
        offered = host.openai_tools + (memory.specs if memory else [])
        calls: list[ToolCall] = []
        if prefetch:
            fetched = []
            for i, (name, args) in enumerate(PREFETCH):
                _report(progress, "tool", status="start", name=name, arguments=args)
                result = await host.call(name, args)
                calls.append(host.calls[-1])
                _report(progress, "tool", status="done", call=host.calls[-1])
                fetched.append((f"call_prefetch_{i}", name, args, result))
            messages.append({"role": "assistant", "content": "",
                             "tool_calls": [{"id": cid, "type": "function",
                                             "function": {"name": name, "arguments": json.dumps(args)}}
                                            for cid, name, args, _ in fetched]})
            messages += [{"role": "tool", "tool_call_id": cid, "content": json.dumps(result, ensure_ascii=False)}
                         for cid, _, _, result in fetched]
        for round_ in range(MAX_TOOL_ROUNDS + 1):
            tools = offered if round_ < MAX_TOOL_ROUNDS else None
            _report(progress, "model", round=round_ + 1)
            message, model = await asyncio.to_thread(chat_with_tools, messages, tools)
            if not message.tool_calls:
                return message.content or "", model, calls
            messages.append({"role": "assistant", "content": message.content or "",
                             "tool_calls": [{"id": c.id, "type": "function",
                                             "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                            for c in message.tool_calls]})
            for c in message.tool_calls:
                try:
                    shown = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    shown = {"raw": c.function.arguments}
                _report(progress, "tool", status="start", name=c.function.name, arguments=shown)
                if memory and c.function.name in recall.NAMES:
                    call = memory.call(c.function.name, c.function.arguments)
                    result = call.result
                else:
                    result = await host.call(c.function.name, c.function.arguments)
                    call = host.calls[-1]
                calls.append(call)
                _report(progress, "tool", status="done", call=call)
                messages.append({"role": "tool", "tool_call_id": c.id,
                                 "content": json.dumps(result, ensure_ascii=False)})
    raise AssertionError("unreachable: the last round offers no tools")


def answer(question: str, k: int = 3, user_id: str | None = None, session: store.Session | None = None,
           history: list | None = None, progress: Progress | None = None) -> Answer:
    """Answer a credit question using the corpus and, through MCP tools, the signed-in user's own data.

    Args:
        question: The user's question in plain language.
        k: How many corpus passages to retrieve and give the model (default 3).
        user_id: The signed-in user, from the login session (never from the question text). None answers
            without any user data or tools, as in Task 10.
        session: The user's open memory episode (Task 17). Adds MEMORY to the context and the goal tools.
        history: This session's earlier chat turns (Gradio's message list), so follow-ups have context.
        progress: Optional callback for live progress (Task 18; see ``Progress``).

    Returns:
        An ``Answer`` with the explanation, the passages used, every tool call, the model name, and timings.

    Raises:
        RuntimeError: If the vector store hasn't been built or no API key is configured.
        UnknownUserError: If ``user_id`` is not in the dataset.
        ValueError: If ``session`` belongs to a different user than ``user_id``.
    """
    if session is not None and session.user_id != user_id:
        raise ValueError("the memory session belongs to a different user")
    t0 = time.perf_counter()
    _report(progress, "retrieval", status="start")
    passages = retrieve(question, k=k)
    t1 = time.perf_counter()
    _report(progress, "retrieval", status="done", passages=passages, seconds=t1 - t0)
    memory = recall.context(user_id, session.session) if session is not None else None
    if session is not None:
        remembered = store.load(user_id)
        _report(progress, "memory", goal=remembered.goal,
                sessions=sum(1 for e in remembered.episodes if e.session != session.session and e.turns()))
    messages = [{"role": "system", "content": load_system_prompt()},
                {"role": "system", "content": build_context(passages, user_id, memory)},
                *recall.history_messages(history),
                {"role": "user", "content": question}]
    if user_id:
        tools = recall.MemoryTools(session, question) if session is not None else None
        text, model, calls = asyncio.run(run_agent(messages, user_id, tools, progress))
    else:
        _report(progress, "model", round=1)
        (text, model), calls = chat(messages), []
    _report(progress, "answer", status="done", model=model)
    return Answer(question=question, user_id=user_id, text=text, model=model, passages=passages, tool_calls=calls,
                  retrieval_seconds=t1 - t0, generation_seconds=time.perf_counter() - t1,
                  sources="\n".join(m["content"] for m in messages[1:] if m.get("content")))


def transcript(a: Answer) -> str:
    """Format an answer as a readable terminal transcript (used for Task 10 evidence and the CLI).

    Args:
        a: The answer to format.

    Returns:
        Multi-line text: the question, the retrieved passage ids with similarity scores, each tool call and
        its outcome, the model and timings, and the answer text.
    """
    lines = [f"> {a.question}", "", *([f"[user] {a.user_id}"] if a.user_id else []), f"[retrieval] {len(a.passages)} passages in {a.retrieval_seconds:.1f}s:"]
    lines += [f"  [{i}] {p.id} ({p.category}, similarity {p.score:.3f})" for i, p in enumerate(a.passages, 1)]
    lines += [f"[tool] {c.tool} {json.dumps(c.arguments, ensure_ascii=False)} -> "
              f"{'ok' if c.ok else c.code} ({c.seconds * 1000:.0f} ms)" for c in a.tool_calls]
    lines += [f"[generation] {a.model} in {a.generation_seconds:.1f}s", "", "CreditCoach:", a.text]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ask CreditCoach one question from the command line.")
    parser.add_argument("--user", help="answer as this dataset user, e.g. USR-001 (default: no user data)")
    parser.add_argument("question", nargs="*")
    args = parser.parse_args()
    question = " ".join(args.question) or "why did my credit score drop 20 points?"
    print(transcript(answer(question, user_id=args.user)))

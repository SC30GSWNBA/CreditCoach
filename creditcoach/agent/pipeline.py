"""The question-answering pipeline: user question -> retrieved passages -> grounded, cited explanation.

Built in Task 10; since Task 15 the user's credit data comes from MCP tool calls. For each question it:
    1. Retrieves the 3 most relevant passages from the credit-education corpus (``rag.retrieve``).
    2. Builds the turn context: USER PROFILE holds the signed-in user's interview profile
       (``user_data.load_user_data``), and REFERENCE CONTEXT holds the numbered passages [1]-[3].
    3. Runs the agent loop: the chat model (``llm.chat_with_tools``) may call ``get_score_history`` and
       ``get_account_summary``; the MCP host (``agent.mcp_host``) runs each call on the CreditCoach MCP server
       for the signed-in user only, and the results go back to the model as TOOL RESULTS until it answers.
    4. Returns the answer with its passages, every tool call, and timings.

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
import time
from dataclasses import dataclass, field

from creditcoach.agent.mcp_host import McpHost, ToolCall
from creditcoach.llm import chat, chat_with_tools
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
    """
    question: str
    user_id: str | None
    text: str
    model: str
    passages: list[Result] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    retrieval_seconds: float = 0.0
    generation_seconds: float = 0.0


def build_context(passages: list[Result], user_id: str | None = None) -> str:
    """Build the per-turn context message that the model reads before the question.

    Args:
        passages: Retrieved corpus passages, numbered [1], [2], ... in this order.
        user_id: The signed-in user. Only this user's profile goes into USER PROFILE; their scores and accounts
            come from tool calls. None means no user data at all, with instructions not to invent figures.

    Returns:
        Text with a USER PROFILE section (or an empty TOOL RESULTS section when there is no user) and a
        REFERENCE CONTEXT section listing each passage with its title and source.
    """
    refs = "\n\n".join(f"[{i}] {p.title} (source: {p.metadata['source']})\n{p.text.split(chr(10) * 2, 1)[-1]}"
                       for i, p in enumerate(passages, 1))
    if user_id:
        profile = json.dumps(load_user_data(user_id)["user_profile"], indent=1, ensure_ascii=False)
        user = f"USER PROFILE:\n{USER_SCOPE.format(user_id=user_id)}\n{profile}"
    else:
        user = f"TOOL RESULTS:\n{NO_TOOLS}"
    return f"{user}\n\nREFERENCE CONTEXT (cite the passages you use as [1], [2], ...):\n{refs or '(none)'}"


async def run_agent(messages: list[dict], user_id: str) -> tuple[str, str, list[ToolCall]]:
    """Run the tool-calling loop for one question over MCP.

    The model gets the two tools (without ``user_id``). Each round, any tool calls it makes are run by the MCP
    host for the signed-in user and returned as ``tool`` messages. After ``MAX_TOOL_ROUNDS`` rounds the model must
    answer in text.

    Args:
        messages: System prompt, context and question; extended in place with tool calls and results.
        user_id: The signed-in user, from the login session.

    Returns:
        ``(answer_text, model_used, tool_calls)``.
    """
    async with McpHost(user_id) as host:
        for round_ in range(MAX_TOOL_ROUNDS + 1):
            tools = host.openai_tools if round_ < MAX_TOOL_ROUNDS else None
            message, model = await asyncio.to_thread(chat_with_tools, messages, tools)
            if not message.tool_calls:
                return message.content or "", model, host.calls
            messages.append({"role": "assistant", "content": message.content or "",
                             "tool_calls": [{"id": c.id, "type": "function",
                                             "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                            for c in message.tool_calls]})
            for c in message.tool_calls:
                result = await host.call(c.function.name, c.function.arguments)
                messages.append({"role": "tool", "tool_call_id": c.id,
                                 "content": json.dumps(result, ensure_ascii=False)})
    raise AssertionError("unreachable: the last round offers no tools")


def answer(question: str, k: int = 3, user_id: str | None = None) -> Answer:
    """Answer a credit question using the corpus and, through MCP tools, the signed-in user's own data.

    Args:
        question: The user's question in plain language.
        k: How many corpus passages to retrieve and give the model (default 3).
        user_id: The signed-in user, from the login session (never from the question text). None answers
            without any user data or tools, as in Task 10.

    Returns:
        An ``Answer`` with the explanation, the passages used, every tool call, the model name, and timings.

    Raises:
        RuntimeError: If the vector store hasn't been built or no API key is configured.
        UnknownUserError: If ``user_id`` is not in the dataset.
    """
    t0 = time.perf_counter()
    passages = retrieve(question, k=k)
    t1 = time.perf_counter()
    messages = [{"role": "system", "content": load_system_prompt()},
                {"role": "system", "content": build_context(passages, user_id)},
                {"role": "user", "content": question}]
    if user_id:
        text, model, calls = asyncio.run(run_agent(messages, user_id))
    else:
        (text, model), calls = chat(messages), []
    return Answer(question=question, user_id=user_id, text=text, model=model, passages=passages, tool_calls=calls,
                  retrieval_seconds=t1 - t0, generation_seconds=time.perf_counter() - t1)


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

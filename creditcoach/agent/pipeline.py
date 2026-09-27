"""The question-answering pipeline: user question -> retrieved passages -> grounded, cited explanation.

This is the Week 1 prototype (Task 10). For each question it:
    1. Retrieves the 3 most relevant passages from the credit-education corpus (``rag.retrieve``).
    2. Builds the turn context: TOOL RESULTS holds the signed-in user's own profile, score history and
       accounts (``user_data.load_user_data``), and REFERENCE CONTEXT holds the numbered passages [1]-[3].
    3. Sends the system prompt, the context, and the question to the chat model (``llm.chat``).
    4. Returns the answer with its passages and timings.

With no ``user_id`` (the Task 10 runs), TOOL RESULTS is empty and the model is told to say it can't see
account data and never to state or illustrate account figures. The Gradio UI (``creditcoach.app``) calls
``answer()`` for every chat message with the user id of the person signed in.

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
import json
import time
from dataclasses import dataclass, field

from creditcoach.llm import chat
from creditcoach.prompts import load_system_prompt
from creditcoach.rag.retrieve import Result, retrieve
from creditcoach.user_data import load_user_data

NO_TOOLS = ("(none: account tools are not connected yet, so no data about this user is available this turn. "
            "Say briefly that you can't see their account data yet, explain the likely causes from the reference "
            "context, and don't state or illustrate any account figures, not even hypothetical example amounts.)")
USER_SCOPE = ("The data below belongs to the signed-in user ({user_id}) and is the only user data you have. "
              "You have no access to any other user's data.")


@dataclass
class Answer:
    """One answered question, with everything needed to show or audit it.

    Attributes:
        question: The user's question, as asked.
        user_id: The signed-in user whose data was in TOOL RESULTS, or None if no user data was used.
        text: The model's explanation, citing passages as [1], [2], ...
        model: The OpenRouter model that wrote the answer (shows if the fallback was used).
        passages: The retrieved corpus passages, in the order they were numbered for the model.
        retrieval_seconds: Time spent searching the corpus.
        generation_seconds: Time the chat model took to answer.
    """
    question: str
    user_id: str | None
    text: str
    model: str
    passages: list[Result] = field(default_factory=list)
    retrieval_seconds: float = 0.0
    generation_seconds: float = 0.0


def build_context(passages: list[Result], user_id: str | None = None) -> str:
    """Build the per-turn context message that the model reads before the question.

    Args:
        passages: Retrieved corpus passages, numbered [1], [2], ... in this order.
        user_id: The signed-in user. Only this user's data goes into TOOL RESULTS. None leaves TOOL RESULTS
            empty, with instructions not to invent figures.

    Returns:
        Text with a TOOL RESULTS section and a REFERENCE CONTEXT section listing each passage with its title
        and source.
    """
    refs = "\n\n".join(f"[{i}] {p.title} (source: {p.metadata['source']})\n{p.text.split(chr(10) * 2, 1)[-1]}"
                       for i, p in enumerate(passages, 1))
    tools = (f"{USER_SCOPE.format(user_id=user_id)}\n{json.dumps(load_user_data(user_id), indent=1, ensure_ascii=False)}"
             if user_id else NO_TOOLS)
    return (f"TOOL RESULTS:\n{tools}\n\n"
            f"REFERENCE CONTEXT (cite the passages you use as [1], [2], ...):\n{refs or '(none)'}")


def answer(question: str, k: int = 3, user_id: str | None = None) -> Answer:
    """Answer a credit question using the corpus and the signed-in user's own data.

    Args:
        question: The user's question in plain language.
        k: How many corpus passages to retrieve and give the model (default 3).
        user_id: The signed-in user, from the login session (never from the question text). None answers
            without any user data, as in Task 10.

    Returns:
        An ``Answer`` with the explanation, the passages used, the model name, and timings.

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
    text, model = chat(messages)
    return Answer(question=question, user_id=user_id, text=text, model=model, passages=passages,
                  retrieval_seconds=t1 - t0, generation_seconds=time.perf_counter() - t1)


def transcript(a: Answer) -> str:
    """Format an answer as a readable terminal transcript (used for Task 10 evidence and the CLI).

    Args:
        a: The answer to format.

    Returns:
        Multi-line text: the question, the retrieved passage ids with similarity scores, the model and
        timings, and the answer text.
    """
    lines = [f"> {a.question}", "", *([f"[user] {a.user_id}"] if a.user_id else []), f"[retrieval] {len(a.passages)} passages in {a.retrieval_seconds:.1f}s:"]
    lines += [f"  [{i}] {p.id} ({p.category}, similarity {p.score:.3f})" for i, p in enumerate(a.passages, 1)]
    lines += [f"[generation] {a.model} in {a.generation_seconds:.1f}s", "", "CreditCoach:", a.text]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ask CreditCoach one question from the command line.")
    parser.add_argument("--user", help="answer as this dataset user, e.g. USR-001 (default: no user data)")
    parser.add_argument("question", nargs="*")
    args = parser.parse_args()
    question = " ".join(args.question) or "why did my credit score drop 20 points?"
    print(transcript(answer(question, user_id=args.user)))

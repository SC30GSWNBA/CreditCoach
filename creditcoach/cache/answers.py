"""The semantic answer cache: the same user asking the same question again gets the stored answer.

An answer costs about 10 seconds and a chat-model call, so this is the layer a user can see. It is also the layer that
can do harm: serving the answer to a *different* question, or an answer built on figures that have since changed.
So a stored answer is used only if all of these hold:

    Same user        Entries live under the signed-in user's own keys. There is no lookup across users.
    Same question    Decided by ``match``, below.
    Same setup       The system prompt, guardrail config, models and corpus are the ones the answer was built
                     with (``version``), and the user's goal and remembered facts are unchanged (``memory``).
    Same figures     The caller compares the user's live tool results with the ones the answer used
                     (``fingerprint``) before serving it. ``agent.pipeline`` does this.
    Fresh            Stored less than ``TTL["answer"]`` ago.

How two questions are judged the same (``match``), in order, after "this year" and "next year" are written as the
year they mean on the day each was asked (``resolve``):

    1. exact            Equal after lower-casing and removing punctuation and extra spaces.
    2. same words       Embedding similarity of at least ``THRESHOLD`` and the same set of meaning-bearing words
                        (contractions, word order, tense, filler words and British spellings don't count).
    3. model-confirmed  Similarity of at least ``CONFIRM_FROM`` otherwise (``ANCHORED_FROM`` when both name the same
                        score or year, ``anchored``), none of the vetoes below, and ``SMALL_MODEL`` agrees the two
                        questions ask for the same thing.

Since 2026-11-10, for a goal asked two ways on Railway: "How can I hit a score of 840 by December next year?" then
"Give me a roadmap to hit 840 by December 2027" missed at 0.628. "next year" isn't "2027" to the numbers and
time-words vetoes, and rewordings of a question naming a target score and date score 0.72 to 0.78, under
``CONFIRM_FROM``. With the year resolved the pair scores 0.724, and from ``ANCHORED_FROM`` the model is asked: it
matched 4 rewordings 3 times out of 3 and refused 5 look-alikes with the same score and date ("Will I hit 840 by
December 2027?", "Save my goal of 840 by December 2027", "...to get a home loan?") 3 times out of 3. Writing the year
also stops "next year" asked in two different years from matching.

Since 2026-10-29 the prompt says that words of degree asking about the same thing ("good", "great", "strong" score)
are the same question, and the model reasons at ``CONFIRM_EFFORT`` "low": on Railway, "What qualifies as a great
credit score?" after "What is a good credit score?" (0.871) was refused three times out of three. Measured on 17
rewordings and 9 look-alikes (``scripts/task22_confirm_band.py``): 14 rewordings hit instead of 13, and still no
look-alike. Showing the model the stored answer was tried and dropped: it let look-alikes through (the answer to
"How do I improve my credit score?" for "How do I improve my credit utilization?").

``CONFIRM_FROM`` is lower than ``THRESHOLD`` because real rewordings can score well under 0.90 ("How do I improve
my credit score?" and "What can I do to raise my credit score?" score 0.852). Measured on 28 pairs (15 rewordings,
13 look-alikes, scripts/task22_confirm_band.py): asking the model from 0.80 matched 14 of the 15 rewordings instead
of 11, and still no look-alike. The cost is one ``SMALL_MODEL`` call (about 2 s) on a miss in that band.

Embedding similarity alone is not enough. Measured with the project's embedding model: "Why did my credit score
drop 20 points this month?" scores 0.996 against "...last month?", 0.955 against "...40 points...", and 0.983
separates "Should I pay off my card in full?" from "Should I not...", while true rewordings score 0.92 to 0.99.
No threshold separates them. Hence the vetoes: questions whose numbers, negation or time words differ are never
matched, whatever their similarity and without asking the model.

Example:
    >>> from creditcoach.cache import answers
    >>> answers.words("Why has my credit score dropped 20 points this month?") == \\
    ...     answers.words("My credit score dropped 20 points this month. Why?")
    True
"""

import json
import logging
import re
import time
import uuid

from creditcoach import cache, config, llm
from creditcoach import observability as obs

log = logging.getLogger("creditcoach.cache")

THRESHOLD = 0.90     # minimum cosine similarity for a "same words" match, with no model call
CONFIRM_FROM = 0.80  # minimum cosine similarity before SMALL_MODEL is asked whether the questions are the same
ANCHORED_FROM = 0.70  # the same, for two questions naming the same score or year (``anchored``)
CONFIRM_EFFORT = "low"  # "minimal" missed "great" for "good" (2026-10-29); "low" matched it with no wrong hit
MAX_PER_USER = 20  # stored answers per user; the oldest goes first

CONTRACTIONS = [(r"\bwhat'?s\b", "what is"), (r"\bhow'?s\b", "how is"), (r"\bwhere'?s\b", "where is"),
                (r"\bcan'?t\b", "can not"), (r"\bwon'?t\b", "will not"), (r"n't\b", " not"), (r"'ll\b", " will"),
                (r"'ve\b", " have"), (r"'re\b", " are"), (r"\bi'm\b", "i am"), (r"'d\b", " would")]
SPELLING = {"utilisation": "utilization", "enquiry": "inquiry", "enquiries": "inquiries", "counselling": "counseling",
            "cheque": "check", "cibil": "credit", "programme": "program"}
FILLER = frozenset("a an the do does did has have had is are am be been being i my me you your please kindly can could "
                   "would to of out up just really actually tell show give and".split())
NEGATION = frozenset("not no never without neither nor none".split())
TIME = [  # (what it means, pattern): two questions that differ in any of these are about different periods
    ("this period", r"\bthis (?:month|year|week|quarter)\b"), ("before", r"\b(?:last|previous|prior|past|ago|earlier)\b"),
    ("after", r"\b(?:next|coming|upcoming|later|future)\b"), ("yesterday", r"\byesterday\b"), ("tomorrow", r"\btomorrow\b"),
    *((m, rf"\b{m}[a-z]*\b") for m in "jan feb mar apr jun jul aug sep oct nov dec".split()), ("may", r"\b(?:in|by|since|of) may\b"),
]
FOLLOW_UP = re.compile(r"\b(?:this|that|these|those|it|they|them|one|ones|instead|same|again|else|other|another|also|"
                       r"then|too|either|both)\b"
                       r"|\b(?:what|as|like|that) you (?:said|suggested|recommended|mentioned|told|advised|described)\b"
                       r"|\byour (?:advice|plan|suggestions?|recommendations?|steps|answer)\b", re.I)
SELF_CONTAINED = re.compile(r"\bthis (?:month|year|week|quarter|time)\b", re.I)

CONFIRM_PROMPT = """Two questions were put to a credit-score assistant by the same user. Decide whether the second \
asks for exactly the same information as the first, so that the answer to the first is a complete and correct \
answer to the second.

Answer "no" if they differ in the time period, a number, the product or account, the direction (rise or fall), \
what is asked (a current figure, a target, a reason, a prediction, advice), or if one is negated. Rewordings count \
as the same: different phrasing, synonyms, and words of degree that ask about the same thing ("good", "great", \
"strong" or "excellent" credit score; "raise" or "boost") are the same question. Otherwise, answer "no" if you are \
unsure. Reply with one word: yes or no."""


RELATIVE_YEARS = [(re.compile(r"\bnext year'?s?\b", re.I), 1), (re.compile(r"\bthis year'?s?\b", re.I), 0)]
ANCHOR = re.compile(r"^(?:[3-8]\d\d|900|20\d\d)$")  # a credit score (300 to 900) or a year


def resolve(question: str, year: int | None = None) -> str:
    """The question with "next year" and "this year" written as the year they mean (``year`` is the year it was
    asked, this one by default): "840 by December next year" is "840 by December 2027" in 2026. "Last year" is left
    as it is, since it often means the last twelve months."""
    year = year or time.gmtime().tm_year
    for pattern, ahead in RELATIVE_YEARS:
        question = pattern.sub(str(year + ahead), question)
    return question


def anchored(question: str) -> bool:
    """Whether a question names a credit score or a year: two questions naming the same ones (the numbers veto sees to
    that) can only differ in what they ask, which ``SMALL_MODEL`` is asked to judge from ``ANCHORED_FROM``."""
    return any(ANCHOR.match(n) for n in numbers(question))


def plain(question: str) -> str:
    """Lower-case with punctuation and extra spaces removed: two questions equal here are an exact match."""
    text = re.sub(r"[‐-―−]", "-", question.lower().replace("’", "'").replace("‘", "'"))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%₹'.-]|(?<!\d)[.](?!\d)", " ", text)).strip(" .-'")


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3 and not word.endswith(("ss", "us", "is")):
            word = word[:-len(suffix)]
            break
    return word[:-1] if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "aeiouls" else word


def words(question: str) -> frozenset[str]:
    """The meaning-bearing words of a question: contractions opened, spellings unified, filler dropped, stemmed."""
    text = plain(question)
    for pattern, full in CONTRACTIONS:
        text = re.sub(pattern, full, text)
    tokens = re.findall(r"\d+(?:[.,]\d+)*%?|[a-z]+(?:-[a-z]+)*", text)
    return frozenset(_stem(SPELLING.get(t, t)) for t in tokens if t not in FILLER)


def numbers(question: str) -> frozenset[str]:
    return frozenset(n.replace(",", "") for n in re.findall(r"\d+(?:[.,]\d+)*", question))


def needs_context(question: str) -> bool:
    """True if the question leans on the conversation ("should I take this loan?", "what about the other one?"), so
    a stored answer must not be reused once there is a conversation to lean on."""
    return bool(FOLLOW_UP.search(SELF_CONTAINED.sub(" ", question)))


def when(question: str) -> frozenset[str]:
    """The periods a question names ("this month", "last ...", "March"). "Now" and "current" are not periods: the
    present is what a question means when it names none."""
    text = plain(question)
    return frozenset(name for name, pattern in TIME if re.search(pattern, text))


def veto(a: str, b: str) -> str | None:
    """Why two questions must not be matched however similar they look, or None."""
    if numbers(a) != numbers(b):
        return "numbers differ"
    if (words(a) & NEGATION) != (words(b) & NEGATION):
        return "negation differs"
    if when(a) != when(b):
        return "time words differ"
    return None


def cosine(a: list[float], b: list[float]) -> float:
    """Dot product of two normalised embeddings."""
    return sum(x * y for x, y in zip(a, b))


def confirm(asked: str, stored: str) -> bool:
    """Ask ``SMALL_MODEL`` whether ``asked`` can be answered with the answer to ``stored``. Any failure is a no."""
    try:
        reply, _ = llm.chat([{"role": "system", "content": CONFIRM_PROMPT},
                             {"role": "user", "content": f"First question: {stored}\nSecond question: {asked}"}],
                            model=config.SMALL_MODEL, effort=CONFIRM_EFFORT)
        return reply.strip().lower().strip(".\"'") == "yes"
    except Exception:
        log.exception("Semantic cache confirmation failed; treating the questions as different")
        return False


def match(question: str, embedding: list[float], entries: list[dict]) -> tuple[dict, str, float] | tuple[None, str, float]:
    """Find a stored question that is the same as ``question``.

    ``question`` and ``embedding`` are of the question with its years resolved (``resolve``), and each entry's
    ``resolved`` is its question resolved on the day it was asked (entries from before 2026-11-10 have none).

    Returns:
        ``(entry, how, similarity)`` with ``how`` one of ``"exact"``, ``"same words"``, ``"model-confirmed"``; or
        ``(None, reason, best_similarity)`` when nothing matches.
    """
    if not entries:
        return None, "nothing stored for this user", 0.0
    text = plain(question)
    for e in entries:
        if e["plain"] == text:
            return e, "exact", 1.0
    similarity, best = max(((cosine(embedding, e["embedding"]), e) for e in entries), key=lambda pair: pair[0])
    stored = best.get("resolved", best["question"])
    lowest = ANCHORED_FROM if anchored(question) else CONFIRM_FROM
    if similarity < lowest:
        return None, f"closest stored question is {similarity:.3f} similar, below {lowest}", similarity
    if reason := veto(question, stored):
        return None, f"{reason} from the closest stored question ({similarity:.3f} similar)", similarity
    if similarity >= THRESHOLD and words(question) == words(stored):
        return best, "same words", similarity
    if config.CACHE_CONFIRM and confirm(question, stored):
        return best, "model-confirmed", similarity
    return None, f"closest stored question ({similarity:.3f} similar) was not confirmed as the same", similarity


def _index_key(user_id: str) -> str:
    return f"cc:{cache.SCHEMA}:answer:{user_id}:index"


def _entries(user_id: str) -> list[dict]:
    raw = cache._try(lambda: cache.backend().get(_index_key(user_id)), "answer", _index_key(user_id))
    now = time.time()
    return [e for e in (json.loads(raw) if raw else []) if now - e["created"] < cache.TTL["answer"]]


def _save_entries(user_id: str, entries: list[dict]) -> None:
    cache._try(lambda: cache.backend().set(_index_key(user_id), json.dumps(entries, ensure_ascii=False),
                                           cache.TTL["answer"]), "answer", _index_key(user_id))


def lookup(user_id: str, question: str, embedding: list[float], version: str, memory: str) -> dict | None:
    """Find a stored answer to this question for this user and setup. Logs a miss; the caller logs the hit, once it
    has checked the figures. ``embedding`` is of the question with its years resolved (``resolve``).

    Returns:
        The stored record (``payload``, ``fingerprint``, ``question``, ``how``, ``similarity``, ``age``), or None.
    """
    usable = [e for e in _entries(user_id) if e["version"] == version and e["memory"] == memory]
    entry, how, similarity = match(resolve(question), embedding, usable)
    if entry is None:
        cache._note("answer", "miss", _index_key(user_id), user_id=user_id, reason=how)
        # kept by Langfuse, unlike events; the closest stored question makes a miss a pair to judge
        # (scripts/cache_misses.py), and is the user's own earlier question, already in their trace
        closest = max(usable, key=lambda e: cosine(embedding, e["embedding"]))["question"] if usable else None
        obs.annotate(**{"cache.reason": how, "cache.similarity": round(similarity, 3), "cache.closest": closest})
        return None
    raw = cache._try(lambda: cache.backend().get(entry["key"]), "answer", entry["key"])
    if raw is None:
        cache._note("answer", "miss", entry["key"], user_id=user_id, reason="the stored answer has expired")
        return None
    return {"payload": json.loads(raw), "fingerprint": entry["fingerprint"], "question": entry["question"], "how": how,
            "similarity": round(similarity, 3), "age": round(time.time() - entry["created"]), "key": entry["key"]}


def store(user_id: str, question: str, embedding: list[float], version: str, memory: str, fingerprint: str,
          payload: dict) -> None:
    """Keep one finished answer for this user, replacing an earlier answer to the same question. ``embedding`` is of
    the question with its years resolved, as for ``lookup``."""
    entry_key = f"cc:{cache.SCHEMA}:answer:{user_id}:{uuid.uuid4().hex[:16]}"
    resolved = resolve(question)
    text = plain(resolved)
    entries = _entries(user_id)
    replaced = [e for e in entries if e["plain"] == text and e["version"] == version and e["memory"] == memory]
    kept = [e for e in entries if e not in replaced]
    kept.append({"key": entry_key, "question": question, "resolved": resolved, "plain": text,
                 "embedding": [round(x, 5) for x in embedding],
                 "version": version, "memory": memory, "fingerprint": fingerprint, "created": time.time()})
    dropped, kept = kept[:-MAX_PER_USER], kept[-MAX_PER_USER:]
    cache._try(lambda: cache.backend().set(entry_key, json.dumps(payload, ensure_ascii=False), cache.TTL["answer"]),
               "answer", entry_key)
    _save_entries(user_id, kept)
    if replaced or dropped:
        cache.delete(*(e["key"] for e in replaced + dropped))
    cache._note("answer", "store", entry_key, user_id=user_id, ttl=cache.TTL["answer"], stored=len(kept))


def forget(user_id: str, key: str) -> None:
    """Drop one stored answer (its figures went stale)."""
    _save_entries(user_id, [e for e in _entries(user_id) if e["key"] != key])
    cache.delete(key)

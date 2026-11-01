"""Usage counters: how many questions CreditCoach has answered and how many people have signed up.

    Where                     What                                     From
    Welcome page (/welcome)   Questions answered, for everyone; and    ``memory.store.answered()``: answers in chat-app
                              people signed up                         sessions only, so eval, evidence and CLI runs
                                                                       never count; ``signup.store.signed_up()``: users
                                                                       made by the Sign up form, not the interview
                                                                       profiles or the sample data
    Above the chat            Questions answered for the signed-in     ``memory.store.answered(user_id)``, across every
                              user, and over how many sessions         session on every machine

Both read Neon (or the memory files without it). The welcome page's figures are kept for ``CACHE_SECONDS``, so its
30-second refresh from every open page asks Neon at most once in that time. A counter that can't be read is left
out, and the page works as before. Only counts are shown: no question, answer or user.

Example:
    >>> public_html()          # the two cards on the welcome page, or "" if neither can be read
    >>> mine_html(5, 2, "2026-10-14T09:00:00.000Z")
"""

import logging
import threading
import time
from datetime import datetime
from html import escape

from creditcoach.memory import store
from creditcoach.signup import store as signup

log = logging.getLogger(__name__)

CACHE_SECONDS = 15
REFRESH_SECONDS = 30  # how often the welcome page asks again
# Counts up from the number shown before to the new one, whenever a counter is drawn; still for reduced motion
COUNT_UP_JS = """() => { setTimeout(() => {
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.querySelectorAll('[data-cc-count]').forEach((el) => {
    const end = Number(el.dataset.ccCount), start = Number(el.dataset.ccShown || 0);
    if (still || start === end) { el.textContent = end.toLocaleString(); el.dataset.ccShown = end; return; }
    const t0 = performance.now();
    const step = (t) => { const k = Math.min(1, (t - t0) / 900);
      el.textContent = Math.round(start + (end - start) * (1 - (1 - k) ** 3)).toLocaleString();
      if (k < 1) requestAnimationFrame(step); else el.dataset.ccShown = end; };
    requestAnimationFrame(step);
  }); }, 50); }"""

_cache: dict = {}
_lock = threading.Lock()


def day(ts: str | None) -> str:
    """An ISO time as a date people read: "3 Oct 2026"."""
    if not ts:
        return ""
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return f"{d.day} {d:%b %Y}"


def counts() -> dict:
    """``{"answers": {...} or None, "signed_up": int or None}``, kept for ``CACHE_SECONDS``; None where it can't be
    read."""
    with _lock:
        if _cache and time.monotonic() - _cache["at"] < CACHE_SECONDS:
            return _cache["counts"]
    found = {"answers": None, "signed_up": None}
    try:
        found["answers"] = store.answered()
    except Exception:
        log.warning("Couldn't count the questions answered", exc_info=True)
    try:
        found["signed_up"] = signup.signed_up()
    except signup.SignupUnavailable:
        pass
    except Exception:
        log.warning("Couldn't count the sign-ups", exc_info=True)
    with _lock:
        _cache.update(at=time.monotonic(), counts=found)
    return found


def _number(n: int) -> str:
    return f'<span class="cc-count-num" data-cc-count="{n}">{n:,}</span>'


def public_html() -> str:
    """The welcome page's cards: questions answered (marked live) and people signed up; "" if neither can be read."""
    c = counts()
    cards = []
    if c["answers"] is not None:
        since = day(c["answers"]["since"])
        cards.append('<div class="cc-count"><div class="cc-count-top"><span class="cc-count-what">Questions answered'
                     '</span><span class="cc-live">Live</span></div>' + _number(c["answers"]["answers"])
                     + f'<span class="cc-count-sub">by CreditCoach for its users{f" since {since}" if since else ""}'
                     "</span></div>")
    if c["signed_up"] is not None:
        cards.append('<div class="cc-count"><div class="cc-count-top"><span class="cc-count-what">People signed up'
                     "</span></div>" + _number(c["signed_up"])
                     + '<span class="cc-count-sub">each with their own practice credit profile</span></div>')
    return f'<div class="cc-counts">{"".join(cards)}</div>' if cards else ""


def mine_html(answers: int, sessions: int, since: str | None) -> str:
    """The signed-in user's counter: questions answered for them so far, across how many sessions."""
    if not answers:
        return ('<div class="cc-mine"><span class="cc-count-what">No questions answered for you yet.</span>'
                '<span class="cc-count-sub">Ask your first one below.</span></div>')
    s = "" if sessions == 1 else "s"
    return (f'<div class="cc-mine">{_number(answers)}<span class="cc-count-what">question{"" if answers == 1 else "s"} '
            f'answered for you so far</span><span class="cc-count-sub">across {sessions} session{s}'
            f'{f" since {escape(day(since))}" if since else ""}</span></div>')


CSS = """
.cc-counts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr)); gap: 12px; }
.cc-count { border: 1.5px solid rgba(79, 70, 229, .35); background: rgba(79, 70, 229, .07); border-radius: 12px;
  padding: 14px 16px; display: grid; gap: 2px; }
.cc-count-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.cc-count-what { font-size: 1rem; font-weight: 600; color: var(--body-text-color); }
.cc-count-num { font-size: 2.1rem; font-weight: 800; line-height: 1.1; font-variant-numeric: tabular-nums;
  color: var(--body-text-color); }
.cc-count-sub { font-size: .86rem; color: var(--body-text-color-subdued); }
.cc-live { display: inline-flex; align-items: center; gap: 6px; font-size: .75rem; font-weight: 700;
  letter-spacing: .06em; text-transform: uppercase; color: #059669; }
.cc-live::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: #059669;
  animation: cc-pulse 2s ease-out infinite; }
@keyframes cc-pulse { 0% { box-shadow: 0 0 0 0 rgba(5, 150, 105, .55); } 100% { box-shadow: 0 0 0 8px rgba(5, 150, 105, 0); } }
@media (prefers-reduced-motion: reduce) { .cc-live::before { animation: none; } }
.cc-mine { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px; border: 1.5px solid rgba(79, 70, 229, .35);
  background: rgba(79, 70, 229, .07); border-radius: 12px; padding: 10px 14px; }
.cc-mine .cc-count-num { font-size: 1.5rem; }
.cc-mine .cc-count-sub { flex-basis: 100%; }
"""

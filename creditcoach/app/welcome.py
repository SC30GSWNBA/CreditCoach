"""The welcome page: "Log in" for people who have a CreditCoach User ID and "Sign up" for people who don't.

It is the first page of the app, served at ``/welcome`` by ``creditcoach.app.server``, with no login needed.

    Log in    User ID and password, checked with ``auth.check_login`` (team logins and sign-up logins alike). A
              correct login gets a one-time ticket and the browser is sent to ``/auth/enter``, which signs it in
              (``creditcoach.app.sessions``) and opens the chat UI.
    Sign up   The privacy note, then the interview questions (``creditcoach.signup.questions``): 10 required, marked
              with a red asterisk, and 14 optional. Nothing is created until every required question is answered
              and the consent box is ticked; both are checked on the server. Then ``signup.store.create_account``
              writes the practice profile and the login to Neon.
    Pop-up    Shows the new User ID and the 16-character password once, with copy buttons, and can email them
              (``creditcoach.signup.mailer``, if a mail account is configured). The person confirms they saved
              them, and lands on Log in with a success note and the User ID filled in.

Sign-up needs Neon. Without it the Sign up tab says so and Log in still works for the team logins. When
``config.INVITE_CODE`` is set the form asks for it, and sign-up closes at ``config.SIGNUP_MAX`` people.
"""

import hmac
import logging

import gradio as gr

from creditcoach import auth, config
from creditcoach.app import counters, sessions
from creditcoach.signup import mailer, questions, store

log = logging.getLogger(__name__)

TAGLINE = "# CreditCoach\nPlain-language answers about credit scores. Not financial advice."
SIGNUP_INTRO = ("New here? Answer 10 short questions (about 2 minutes) and CreditCoach creates a practice profile and "
                "a login for you.")
CONSENT = ("I understand that the scores and accounts CreditCoach shows me are a practice profile built from my "
           "answers, not my real credit report.")
REQUIRED_NOTE = ('<div class="cc-req-note"><span class="cc-star">*</span> Required: please answer every question in '
                 'this section.</div>')
NO_RESET = ("CreditCoach keeps only a scrambled copy of your password, so it <b>can't show it again or reset it</b>. "
            "If you lose it and have no emailed copy, you'll need to sign up again as a new user.")
NO_DATABASE = ("Sign-up isn't available on this copy of CreditCoach, because it isn't connected to its database. "
               "If you already have a User ID, the Log in tab works as usual.")
# After a correct login: open /auth/enter with the one-time ticket, which sets the session cookie
ENTER_JS = "(t) => { if (t) { window.location.href = '/auth/enter?t=' + encodeURIComponent(t); } }"

CSS = """
.cc-welcome {max-width: 860px; margin: 0 auto;}
.cc-modal {position: fixed !important; inset: 0; z-index: 1000; background: rgba(15, 23, 42, .62);
           display: flex; align-items: center; justify-content: flex-start; padding: 16px; overflow-y: auto;}
.cc-modal > .cc-card {max-width: 560px; width: 100%; min-width: 0; box-sizing: border-box; margin: auto;
           background: var(--background-fill-primary); border-radius: 14px; padding: 20px 22px;
           box-shadow: 0 20px 60px rgba(0,0,0,.35); gap: 10px !important; flex-grow: 0 !important;}
.cc-card > *, .cc-card .cc-email, .cc-card .cc-email > * {flex-grow: 0 !important;}
/* A note with nothing in it takes no room */
.cc-note {min-height: 0 !important; padding: 0 !important; margin: 0 !important;}
.cc-note:not(:has(.cc-ok, .cc-warn, .cc-err)) {display: none !important;}
/* Nothing in the pop-up may shrink or scroll on its own: on a short window the whole pop-up scrolls instead, so the
   User ID and password are always shown in full, one above the other. */
.cc-card, .cc-card * {flex-shrink: 0 !important;}
.cc-card .form, .cc-card .block, .cc-card .gap, .cc-card .column, .cc-card .row {overflow: visible !important;
           min-height: 0 !important;}
.cc-card .cc-secret textarea, .cc-card .cc-secret input {overflow: hidden !important; white-space: nowrap; resize: none;}
.cc-warn {border-left: 4px solid #d97706; padding: 8px 12px; background: rgba(217,119,6,.10); border-radius: 6px;}
.cc-ok {border-left: 4px solid #059669; padding: 8px 12px; background: rgba(5,150,105,.10); border-radius: 6px;}
.cc-err {border-left: 4px solid #dc2626; padding: 8px 12px; background: rgba(220,38,38,.08); border-radius: 6px;}
.cc-welcome {--checkbox-border-color: #475569; --checkbox-border-width: 2px;
           --checkbox-border-color-hover: #4f46e5; --checkbox-border-color-focus: #4f46e5;
           --checkbox-background-color: #ffffff; --checkbox-background-color-selected: #4f46e5;
           --checkbox-border-color-selected: #4f46e5;}
.cc-welcome fieldset label, .cc-welcome .cc-tick label {border: 1.5px solid #94a3b8 !important; border-radius: 10px !important;
           padding: 9px 14px !important; background: var(--background-fill-primary) !important; cursor: pointer;}
.cc-welcome fieldset label:hover {border-color: #4f46e5 !important;}
.cc-welcome fieldset label.selected, .cc-welcome fieldset label:has(input:checked) {border-color: #4f46e5 !important;
           background: rgba(79, 70, 229, .12) !important; box-shadow: 0 0 0 1px #4f46e5 inset;}
.cc-welcome input[type=radio], .cc-welcome input[type=checkbox] {width: 20px !important; height: 20px !important;
           min-width: 20px; border: 2px solid #475569 !important; background-color: #fff; margin-right: 4px;}
.cc-welcome input[type=radio]:checked, .cc-welcome input[type=checkbox]:checked {border-color: #4f46e5 !important;
           background-color: #4f46e5 !important;}
.cc-welcome fieldset label span {font-size: .98rem; color: #0f172a !important;}
.cc-welcome fieldset label.selected span, .cc-welcome fieldset label:has(input:checked) span {
           color: #1e1b4b !important; font-weight: 700;}
.cc-welcome fieldset > span, .cc-welcome fieldset [data-testid="block-info"] {font-weight: 600; font-size: 1rem; margin-bottom: 6px;}
.cc-welcome input[type=text], .cc-welcome input[type=password], .cc-welcome input[type=email], .cc-welcome textarea {
           border: 1.5px solid #64748b !important; border-radius: 8px !important; background: #ffffff !important;
           color: #0f172a !important; padding: 10px 12px !important; box-shadow: none !important;}
.cc-welcome input[type=text]:focus, .cc-welcome input[type=password]:focus, .cc-welcome input[type=email]:focus,
.cc-welcome textarea:focus {border-color: #4f46e5 !important; box-shadow: 0 0 0 3px rgba(79, 70, 229, .25) !important;
           outline: none !important;}
.cc-welcome input::placeholder, .cc-welcome textarea::placeholder {color: #94a3b8 !important;}
.cc-section {border: 1.5px solid #cbd5e1 !important; border-radius: 12px !important; margin-top: 14px;}
.cc-section > button.label-wrap, .cc-section .label-wrap {padding: 6px 4px 10px !important; margin-bottom: 8px;
           border-bottom: 2px solid #4f46e5;}
.cc-section > button.label-wrap > span, .cc-section .label-wrap > span {font-size: 1.35rem !important;
           font-weight: 700 !important; color: var(--body-text-color) !important; letter-spacing: -.01em;}
.cc-welcome .tab-container, .cc-welcome .tab-wrapper {height: auto !important; overflow: visible !important;}
.cc-welcome .tab-container {gap: 10px !important; padding: 6px !important; background: #e2e8f0; border-radius: 14px;
           display: flex !important; width: 100%;}
.cc-welcome .tab-container::after {display: none !important;}
.cc-welcome button[role="tab"] {flex: 1 1 0; font-size: 1.15rem !important; font-weight: 700 !important;
           padding: 12px 18px !important; height: auto !important; border-radius: 10px !important;
           border: 1.5px solid transparent !important; color: #475569 !important; background: transparent !important;
           justify-content: center; text-align: center;}
.cc-welcome button[role="tab"]:hover {color: #4f46e5 !important; border-color: #4f46e5 !important;}
.cc-welcome button[role="tab"].selected, .cc-welcome button[role="tab"][aria-selected="true"] {
           background: #4f46e5 !important; color: #ffffff !important; border-color: #4f46e5 !important;
           box-shadow: 0 2px 8px rgba(79, 70, 229, .35);}
.cc-welcome button[role="tab"]::after, .cc-welcome button[role="tab"].selected::after {display: none !important;}
.cc-copy p, .cc-copy li {font-size: 1.07rem !important; line-height: 1.55 !important;}
.cc-copy h3 {font-size: 1.22rem !important; margin-top: .4em;}
.cc-copy li {margin-bottom: 4px;}
.cc-required fieldset > span::after, .cc-required [data-testid="block-info"]::after {content: " *"; color: #dc2626;
           font-weight: 800; font-size: 1.15em;}
.cc-req-note {font-size: .98rem; font-weight: 600; color: #475569; margin: 2px 0 6px;}
.cc-star {color: #dc2626; font-weight: 800; font-size: 1.15em;}
.cc-secret textarea, .cc-secret input {font-family: ui-monospace, Menlo, monospace; font-size: 1.05rem;}
"""


def box(kind: str, text: str) -> str:
    """A coloured note: ``kind`` is "ok", "warn" or "err". Empty text gives an empty string (clears the note)."""
    return f'<div class="cc-{kind}">{text}</div>' if text else ""


def log_in(username: str, password: str) -> tuple[str, str]:
    """Check a login. Returns ``(note, ticket)``; the ticket is empty unless the login was correct."""
    username = (username or "").strip()
    if sessions.too_many_failures(username):
        return box("err", "Too many attempts for this User ID. Please wait 15 minutes and try again."), ""
    if not auth.check_login(username, password or ""):
        sessions.note_failure(username)
        return box("err", "That User ID and password don't match. Check both and try again."), ""
    return box("ok", "Signed in. Opening CreditCoach…"), sessions.issue_ticket(username)


def sign_up(first_name, gender, invite, agreed, *values) -> tuple:
    """Create an account from the form. Returns ``(note, pop-up visibility, username, password)``.

    Nothing is created unless every required question is answered, the consent box is ticked and, when one is
    set, the invite code matches.
    """
    stay = (gr.skip(), gr.skip(), gr.skip())
    answers = questions.clean(first_name, gender, values)
    missing = questions.missing(answers)
    if missing:
        return (box("err", "Please answer: <ul>" + "".join(f"<li>{m}</li>" for m in missing) + "</ul>"), *stay)
    if config.INVITE_CODE and not hmac.compare_digest((invite or "").strip().encode(), config.INVITE_CODE.encode()):
        return (box("err", "That invite code isn't right. Check it with the person who invited you."), *stay)
    if not agreed:
        return (box("err", "Please tick the box above the button to continue."), *stay)
    try:
        made = store.create_account(answers)
    except store.SignupClosed:
        return (box("warn", "Sign-ups are full for now. Thank you for your interest in CreditCoach."), *stay)
    except Exception:
        log.exception("Sign-up failed")
        return (box("err", "Sorry, we couldn't create your login just now. Nothing was saved; please try again."),
                *stay)
    return "", gr.update(visible=True), made["username"], made["password"]


def email_login(address: str, username: str, password: str) -> str:
    """Email the login shown in the pop-up to ``address``. The address is not kept."""
    address = (address or "").strip()
    if not mailer.valid(address):
        return box("err", "That doesn't look like an email address.")
    if not (username and password):
        return box("err", "There is no new login to send.")
    try:
        mailer.send_login(address, username, password)
    except Exception as exc:  # the address and password stay out of the log
        log.error("Couldn't send a login email: %s", type(exc).__name__)
        return box("warn", "The email couldn't be sent. Please copy your User ID and password instead.")
    return box("ok", "Sent. Check your inbox (and spam folder). We have not kept your email address.")


def build() -> gr.Blocks:
    """Create the welcome page (not yet served; ``creditcoach.app.server`` mounts it at ``/welcome``)."""
    can_sign_up = store.available()
    with gr.Blocks(title="CreditCoach", analytics_enabled=False) as page:
        with gr.Column(elem_classes="cc-welcome"):
            gr.Markdown(TAGLINE, elem_classes="cc-copy")
            proof = gr.HTML(visible=False)  # questions answered and people signed up (app.counters)
            with gr.Tabs(selected="login") as tabs:
                with gr.Tab("Log in", id="login"):
                    created = gr.HTML()
                    gr.Markdown("Already have a CreditCoach User ID? Sign in here.", elem_classes="cc-copy")
                    username = gr.Textbox(label="User ID", placeholder="creditcoach_user16")
                    password = gr.Textbox(label="Password", type="password")
                    login_btn = gr.Button("Log in", variant="primary")
                    login_msg = gr.HTML()
                    ticket = gr.Textbox(visible=False)
                with gr.Tab("Sign up", id="signup"):
                    if not can_sign_up:
                        gr.HTML(box("warn", NO_DATABASE))
                    with gr.Column(visible=can_sign_up):
                        gr.Markdown(SIGNUP_INTRO, elem_classes="cc-copy")
                        gr.Markdown(questions.PRIVACY, elem_classes="cc-copy")
                        first_name = gr.Textbox(max_length=30, label="What should CreditCoach call you? (optional; a "
                                                                     "nickname is fine)")
                        gender = gr.Radio(questions.GENDERS, label="Gender (optional)")
                        inputs = []
                        for title, required, section in questions.SECTIONS:
                            with gr.Accordion(title, open=required, elem_classes="cc-section"):
                                if required:
                                    gr.HTML(REQUIRED_NOTE)
                                for _, kind, label, options, needed in section:
                                    make = gr.CheckboxGroup if kind == questions.MULTI else gr.Radio
                                    inputs.append(make(options, label=label + ("" if needed else " (optional)"),
                                                       elem_classes="cc-required" if needed else None))
                        invite = gr.Textbox(label="Invite code", visible=bool(config.INVITE_CODE),
                                            elem_classes="cc-required")
                        agree = gr.Checkbox(label=CONSENT, elem_classes="cc-tick")
                        signup_btn = gr.Button("Create my CreditCoach login", variant="primary")
                        signup_msg = gr.HTML()

            with gr.Column(visible=False, elem_classes="cc-modal") as modal:
                with gr.Column(elem_classes="cc-card"):
                    gr.Markdown("## Your CreditCoach login is ready\nCopy both now. **This is the only time the "
                                "password is shown.**")
                    new_user = gr.Textbox(label="User ID", interactive=False, buttons=["copy"],
                                          elem_classes="cc-secret")
                    new_pass = gr.Textbox(label="Password (16 characters)", interactive=False, buttons=["copy"],
                                          elem_classes="cc-secret")
                    gr.HTML(box("warn", NO_RESET))
                    with gr.Column(visible=mailer.configured(), elem_classes="cc-email"):
                        gr.Markdown("**Backup (optional):** email these details to yourself. The address is used "
                                    "for this one message and is not stored.")
                        with gr.Row():
                            email = gr.Textbox(show_label=False, placeholder="you@example.com", scale=3,
                                               container=False)
                            email_btn = gr.Button("Email me my login", scale=1, min_width=150)
                        email_msg = gr.HTML(elem_classes="cc-note")
                    saved = gr.Checkbox(label="I have saved my User ID and password", elem_classes="cc-tick")
                    done_btn = gr.Button("Continue to Log in", variant="primary")
                    done_msg = gr.HTML(elem_classes="cc-note")

        def show_counts() -> dict:
            """The counters, or nothing if neither can be read."""
            html = counters.public_html()
            return gr.update(value=html, visible=bool(html))

        gr.on([page.load, gr.Timer(counters.REFRESH_SECONDS).tick], show_counts, outputs=proof,
              show_progress="hidden", api_name=False).then(None, js=counters.COUNT_UP_JS)
        gr.on([login_btn.click, password.submit], log_in, [username, password], [login_msg, ticket],
              api_name="log_in").then(None, ticket, None, js=ENTER_JS)
        signup_btn.click(sign_up, [first_name, gender, invite, agree, *inputs],
                         [signup_msg, modal, new_user, new_pass], api_name="sign_up", concurrency_limit=2)
        email_btn.click(email_login, [email, new_user, new_pass], email_msg, api_name="email_login")

        def done(saved_them: bool, new_username: str) -> tuple:
            """Close the pop-up and move to Log in, once the person confirms they saved the login."""
            if not saved_them:
                return (box("err", "Please copy your User ID and password, then tick the box."),
                        *[gr.skip()] * (11 + len(inputs)))
            note = box("ok", f"Your login <b>{new_username}</b> and password were created successfully. Sign in "
                             "below to start using CreditCoach.")
            return ("", gr.update(visible=False), "", "", "", "", False, note, new_username, gr.Tabs(selected="login"),
                    "", False, *[gr.update(value=None) for _ in inputs])

        done_btn.click(done, [saved, new_user],
                       [done_msg, modal, new_pass, new_user, email, email_msg, saved, created, username, tabs,
                        first_name, agree, *inputs], api_name="done")
    return page

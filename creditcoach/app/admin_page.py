"""The admin's pages: sign-in at ``/admin`` and the Dashboard for every user at ``/admin/dashboard``.

    /admin/             Admin email and password (``admin.check``), at most ``sessions.ADMIN_FAILURES`` wrong tries
                        in 15 minutes. "Forgot password?" emails a one-time reset link to the admin address; opening
                        it (``/admin/?reset=<token>``) shows the form that sets a new password.
    /admin/dashboard/   The Dashboard (``dashboard_ui`` in admin mode): every user's answers or one user's, real use
                        and eval and test runs, with all the detail. "Change password" asks for the current password
                        and a new one; the new one is emailed to the admin address. "Log out" ends the session.

A correct sign-in, a new password and a reset all end the same way: a one-time ticket that ``/admin/enter``
(``app.server``) swaps for the admin cookie. A new password changes the cookie's epoch (``sessions.admin_cookie``),
so every other admin session is signed out and this one gets a fresh cookie.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import gradio as gr

from creditcoach import admin, config
from creditcoach.app import dashboard_ui, sessions
from creditcoach.app.welcome import box
from creditcoach.signup import mailer
from creditcoach.user_data import first_names

log = logging.getLogger("creditcoach.app")

FAILURE_KEY = "\0admin"  # the failed-sign-in count's key: no username can collide with it
ENTER_JS = ("(t, note) => { if (t) { window.location.href = '/admin/enter?t=' + encodeURIComponent(t) + "
            "(note ? '&note=' + note : ''); } }")
NOT_SET_UP = ("The admin sign-in isn't set up on this server. Set CREDITCOACH_ADMIN_PASSWORD on the server and "
              "restart it.")
SAVING = "Saving the new password and emailing it to you. This can take up to 20 seconds…"
NOTES = {  # shown at the top of the Dashboard after a new password (``/admin/enter?note=``)
    "sent": ("ok", f"Password changed. We've emailed the new password to {admin.EMAIL}."),
    "unsent": ("warn", "Password changed, but the email couldn't be sent. Please note the new password now."),
}


def waiting(text: str):
    """A handler that shows ``text`` as a "still working" note at once. The slow step runs after it with Gradio's own
    progress hidden, which otherwise squeezes a timer into the empty note at the foot of the card."""
    return lambda: box("wait", text)


def when() -> str:
    """Now, as the admin's emails give it: India time, since CreditCoach is for credit scores in India."""
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y at %H:%M IST")


def email_password(password: str) -> str:
    """Email a new password to the admin; "sent" or "unsent" (``NOTES``)."""
    try:
        mailer.send_admin_password(password, when())
    except Exception as exc:  # the password stays out of the log
        log.error("Couldn't send the admin password email: %s", mailer.why(exc))
        return "unsent"
    return "sent"


# ---------------------------------------------------------------- sign-in

def sign_in(email: str, password: str) -> tuple[str, str]:
    """Check the admin's sign-in. Returns ``(note, ticket)``; the ticket is empty unless it was right."""
    if not admin.configured():
        return box("err", NOT_SET_UP), ""
    if sessions.too_many_failures(FAILURE_KEY, sessions.ADMIN_FAILURES):
        return box("err", "Too many wrong tries. Please wait 15 minutes and try again."), ""
    if not admin.check(email, password):
        sessions.note_failure(FAILURE_KEY)
        left = sessions.ADMIN_FAILURES - sessions.recent_failures(FAILURE_KEY)
        more = f" {left} {'try' if left == 1 else 'tries'} left before a 15-minute pause." if left > 0 else ""
        return box("err", "That email and password don't match." + more), ""
    return box("ok", "Signed in. Opening the Dashboard…"), sessions.issue_ticket(sessions.ADMIN, kind="admin")


def forgot() -> str:
    """Email a one-time reset link to the admin address. The note is the same whoever asks."""
    if not mailer.configured():
        return box("warn", "Email isn't set up on this server, so a reset link can't be sent.")
    try:
        token = admin.start_reset()
    except admin.AdminError as exc:
        return box("err", str(exc))
    try:
        mailer.send_admin_reset(f"{config.PUBLIC_URL}/admin/?reset={token}")
    except Exception as exc:
        log.error("Couldn't send the admin reset email: %s", mailer.why(exc))
        return box("warn", "The reset email couldn't be sent. Please try again in a few minutes.")
    return box("ok", f"A reset link is on its way to {admin.EMAIL}. It works once, for 30 minutes.")


def opened(request: gr.Request) -> tuple:
    """On page load: the reset form when the address carries a working reset link, else the sign-in form (with a
    note if the link was stale)."""
    token = (getattr(request, "query_params", None) or {}).get("reset", "")
    if not token:
        return gr.update(visible=True), gr.update(visible=False), "", ""
    if admin.reset_valid(token):
        return gr.update(visible=False), gr.update(visible=True), token, ""
    return (gr.update(visible=True), gr.update(visible=False), "",
            box("err", "This reset link has expired or was already used. Ask for a new one below."))


def set_new(token: str, new: str, confirm: str) -> tuple[str, str, str]:
    """Set a new password from a reset link, email it, and sign in. Returns ``(note, ticket, email note)``."""
    try:
        admin.finish_reset(token, new or "", confirm or "")
    except admin.AdminError as exc:
        return box("err", str(exc)), "", ""
    return box("ok", "Password changed. Opening the Dashboard…"), sessions.issue_ticket(
        sessions.ADMIN, kind="admin"), email_password(new)


def signin() -> gr.Blocks:
    """The sign-in page (not yet served; ``app.server`` mounts it at ``/admin``)."""
    with gr.Blocks(title="CreditCoach admin", analytics_enabled=False) as page:
        with gr.Column(elem_classes="cc-welcome cc-admin"):
            gr.HTML('<a class="cc-back" href="/welcome/">← Back to CreditCoach</a>')
            with gr.Column(elem_classes="cc-admin-card") as signin_col:
                gr.Markdown("## Admin sign-in\nFor the CreditCoach admin only. Opens the Dashboard for every user.",
                            elem_classes="cc-copy")
                email = gr.Textbox(label="Admin email", placeholder="name@example.com")
                password = gr.Textbox(label="Password", type="password")
                go = gr.Button("Sign in", variant="primary")
                lost = gr.Button("Forgot password?", size="sm", variant="secondary", elem_classes="cc-forgot")
                note = gr.HTML()
            with gr.Column(visible=False, elem_classes="cc-admin-card") as reset_col:
                gr.Markdown("## Set a new admin password\nOpened from the link in the reset email.",
                            elem_classes="cc-copy")
                new = gr.Textbox(label="New password", type="password")
                confirm = gr.Textbox(label="Confirm new password", type="password")
                gr.Markdown(f"At least {admin.MIN_LENGTH} characters. The new password is emailed to the admin "
                            "address.", elem_classes="cc-copy")
                save = gr.Button("Save and open the Dashboard", variant="primary")
                reset_note = gr.HTML()
            token = gr.State("")
            ticket = gr.Textbox(visible=False)
            sent = gr.Textbox(visible=False)
        page.load(opened, outputs=[signin_col, reset_col, token, note], api_name=False)
        gr.on([go.click, password.submit], sign_in, [email, password], [note, ticket], api_name=False).then(
            None, [ticket, sent], None, js=ENTER_JS)
        lost.click(waiting("Sending the reset link…"), outputs=note, show_progress="hidden", api_name=False).then(
            forgot, outputs=note, show_progress="hidden", api_name=False)
        gr.on([save.click, confirm.submit], waiting(SAVING), outputs=reset_note, show_progress="hidden",
              api_name=False).then(set_new, [token, new, confirm], [reset_note, ticket, sent], show_progress="hidden",
                                   api_name=False).then(None, [ticket, sent], None, js=ENTER_JS)
    return page


# ---------------------------------------------------------------- the Dashboard

def change(current: str, new: str, confirm: str, request: gr.Request) -> tuple[str, str, str]:
    """"Save new password": check, store and email it, then sign in afresh under it. Returns ``(note, ticket,
    email note)``."""
    if is_admin(request) is None:
        return box("err", "Please sign in again."), "", ""
    try:
        admin.change(current or "", new or "", confirm or "")
    except admin.AdminError as exc:
        return box("err", str(exc)), "", ""
    return box("ok", "Password changed."), sessions.issue_ticket(sessions.ADMIN, kind="admin"), email_password(new)


def users() -> list[tuple[str, str]]:
    """The User choice's entries after "All users": every user id in the dataset with its name."""
    try:
        return [(f"{u} · {name}" if name != u else u, u) for u, name in first_names().items()]
    except Exception:
        log.exception("Couldn't list the users for the admin's User choice")
        return []


def arrived(request: gr.Request) -> tuple:
    """On page load: the note after a new password, if any, and the User choice with everyone signed up so far."""
    kind, text = NOTES.get((getattr(request, "query_params", None) or {}).get("note", ""), ("", ""))
    return box(kind, text) if kind else "", gr.update(choices=[("All users", dashboard_ui.ALL_USERS), *users()])


def is_admin(request: gr.Request) -> str | None:
    """The admin page's viewer: Gradio already let only the admin in (``auth_dependency``); checked again here."""
    return sessions.ADMIN if getattr(request, "username", None) == sessions.ADMIN else None


def dashboard() -> gr.Blocks:
    """The admin's Dashboard page (not yet served; ``app.server`` mounts it at ``/admin/dashboard``)."""
    with gr.Blocks(title="CreditCoach admin", analytics_enabled=False) as page:
        with gr.Row():
            gr.Markdown(f"Signed in as **Admin** ({admin.EMAIL})", elem_classes="cc-who")
            change_btn = gr.Button("Change password", size="sm", scale=0, min_width=190, elem_classes="cc-logout")
            logout = gr.Button("Log out", size="sm", scale=0, elem_classes="cc-logout")
        top_note = gr.HTML()
        with gr.Column(visible=False, elem_classes="cc-modal") as modal:
            with gr.Column(elem_classes="cc-card"):
                gr.Markdown("## Change admin password")
                current = gr.Textbox(label="Current password", type="password")
                new = gr.Textbox(label="New password", type="password")
                confirm = gr.Textbox(label="Confirm new password", type="password")
                gr.Markdown(f"At least {admin.MIN_LENGTH} characters, and not the same as the current one. The new "
                            f"password is emailed to {admin.EMAIL}.")
                with gr.Row():
                    save = gr.Button("Save new password", variant="primary")
                    cancel = gr.Button("Cancel")
                note = gr.HTML()
        with gr.Tabs():
            with gr.Tab("Dashboard"):
                dash = dashboard_ui.build(is_admin, admin=True)
        ticket = gr.Textbox(visible=False)
        sent = gr.Textbox(visible=False)

        page.load(arrived, outputs=[top_note, dash.user], show_progress="hidden", api_name=False)
        page.load(dash.fill, dash.inputs, dash.outputs, api_name=False)
        logout.click(None, js="() => { window.location.href = '/admin/logout'; }")
        change_btn.click(lambda: (gr.update(visible=True), "", "", "", ""), outputs=[modal, current, new, confirm, note],
                         api_name=False)
        cancel.click(lambda: (gr.update(visible=False), "", "", ""), outputs=[modal, current, new, confirm],
                     api_name=False)
        gr.on([save.click, confirm.submit], waiting(SAVING), outputs=note, show_progress="hidden",
              api_name=False).then(change, [current, new, confirm], [note, ticket, sent], show_progress="hidden",
                                   api_name=False).then(None, [ticket, sent], None, js=ENTER_JS)
    return page


CSS = """
.cc-admin {max-width: 520px;}
.cc-admin .cc-back {font-size: .95rem;}
.cc-admin-card {border: 1.5px solid #cbd5e1; border-radius: 14px; padding: 18px 20px !important;}
.cc-forgot {align-self: flex-start; border: none !important; background: none !important; box-shadow: none !important;
  color: #4f46e5 !important; text-decoration: underline; padding: 0 !important; min-width: 0 !important;}
.dark .cc-forgot {color: #a5b4fc !important;}
"""

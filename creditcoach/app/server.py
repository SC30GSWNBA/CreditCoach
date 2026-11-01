"""The web server: the welcome page and the chat UI behind one address, with sign-in between them.

    /            Goes to the chat UI if the browser is signed in, else to the welcome page.
    /welcome/    Log in and Sign up (``creditcoach.app.welcome``). No login needed.
    /auth/enter  Swaps the one-time ticket from a correct login for the session cookie, then opens the chat UI.
    /app/        The chat UI (``creditcoach.app.main.build``). Every request needs the session cookie
                 (``sessions.current_user``); Gradio puts the username in ``request.username``, as its own login
                 page used to.
    /logout      Clears the cookie and returns to the welcome page (the chat UI's "Log out" button goes here).

Both pages are Gradio apps mounted on one FastAPI app, because Gradio's built-in login page has no room for a
"Sign up" tab. ``run`` serves it on 127.0.0.1 and, with ``share=True``, opens the same public gradio.live tunnel
``demo.launch(share=True)`` would.
"""

import logging
import secrets
import threading
import time

import gradio as gr
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from gradio import networking

from creditcoach import auth
from creditcoach.app import counters, sessions, welcome

log = logging.getLogger("creditcoach.app")

APP_PATH, WELCOME_PATH = "/app", "/welcome"


def secure(request: Request) -> bool:
    """Whether the browser reached us over HTTPS (directly or through the share tunnel)."""
    return "https" in (request.headers.get("x-forwarded-proto", ""), request.url.scheme)


def create(demo: gr.Blocks, css: str = "") -> FastAPI:
    """The FastAPI app: the routes above, the welcome page, and ``demo`` (the chat UI) behind sign-in."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def welcome_instead_of_401(request: Request, call_next):
        """Opening the chat UI without being signed in shows the welcome page, not Gradio's "not authenticated"."""
        if request.url.path.rstrip("/") == APP_PATH and sessions.current_user(request) is None:
            return RedirectResponse(WELCOME_PATH + "/")
        return await call_next(request)

    @app.get("/")
    def home(request: Request):
        return RedirectResponse((APP_PATH if sessions.current_user(request) else WELCOME_PATH) + "/")

    @app.get("/auth/enter")
    def enter(request: Request, t: str = ""):
        username = sessions.redeem_ticket(t)
        if username is None:
            return RedirectResponse(WELCOME_PATH + "/")
        response = RedirectResponse(APP_PATH + "/")
        response.set_cookie(sessions.COOKIE, sessions.cookie_for(username), max_age=sessions.SESSION_SECONDS,
                            httponly=True, samesite="lax", secure=secure(request))
        return response

    @app.get("/logout")
    def logout():
        response = RedirectResponse(WELCOME_PATH + "/")
        response.delete_cookie(sessions.COOKIE)
        return response

    gr.mount_gradio_app(app, welcome.build(), path=WELCOME_PATH, theme=gr.themes.Soft(),
                        css=welcome.CSS + counters.CSS)
    gr.mount_gradio_app(app, demo, path=APP_PATH, auth_dependency=sessions.current_user, theme=gr.themes.Soft(),
                        css=css)
    return app


def run(demo: gr.Blocks, port: int = 7860, share: bool = False, css: str = "", host: str = "127.0.0.1") -> None:
    """Serve the app on ``host:port`` until Ctrl+C, optionally with a public gradio.live link.

    ``host`` is 127.0.0.1 locally. A hosted deployment (Railway) passes 0.0.0.0 to accept its proxy's
    connections, and then the proxy's X-Forwarded-* headers are trusted, so the app sees the visitor's HTTPS.
    """
    hosted = host != "127.0.0.1"
    server = uvicorn.Server(uvicorn.Config(create(demo, css), host=host, port=port, log_level="warning",
                                           forwarded_allow_ips="*" if hosted else None))
    thread = threading.Thread(target=server.run, name="creditcoach-server", daemon=True)
    thread.start()
    while not server.started and thread.is_alive():
        time.sleep(0.05)
    if not thread.is_alive():
        raise SystemExit(f"Couldn't start the server on port {port} (is it already in use?)")
    log.info("CreditCoach running at http://%s:%d (login required; %d team logins; sign-up %s)", host, port,
             len(auth.logins()), "open" if welcome.store.available() else "off: no Neon database")
    if share:
        try:
            url = networking.setup_tunnel("127.0.0.1", port, secrets.token_urlsafe(32), None, None)
            log.info("Public share link (expires in about 1 week, stops when this process stops): %s", url)
        except Exception:
            log.warning("Could not create a share link; the app is available locally only.", exc_info=True)
    try:
        while thread.is_alive():
            thread.join(0.5)
    except KeyboardInterrupt:
        server.should_exit = True
        thread.join(5)

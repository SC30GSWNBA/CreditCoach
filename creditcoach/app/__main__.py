"""Entry point so the UI can be started with ``python -m creditcoach.app``.

It simply runs ``creditcoach.app.main.main()``; all options (``--share``, ``--port``) are defined there.
"""

from creditcoach.app.main import main

main()

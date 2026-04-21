"""``lvt-cert dev`` — run the portal locally via a Flask-compatible dev server.

Maps the Vercel-style ``api/*.py`` handlers to local routes and serves the
static ``templates/`` directory so you can iterate without deploying.

Phase 01 ships a stub; the real shim lands in Phase 05.
"""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(help="Run the portal locally.")
console = Console()


@app.callback(invoke_without_command=True)
def dev(
    port: int = typer.Option(5000, "--port", "-p", min=1, max=65_535, help="Port to bind."),
    host: str = typer.Option("127.0.0.1", help="Host to bind."),
) -> None:
    console.print(f"[yellow]• dev server not implemented yet (Phase 05).[/] Would bind {host}:{port}.")

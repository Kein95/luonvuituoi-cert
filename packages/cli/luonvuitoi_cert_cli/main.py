"""Entry point for the ``lvt-cert`` / ``luonvuitoi-cert`` console script.

Subcommands are declared here and implemented in ``commands/*.py``. Keeping
the dispatch layer thin means ``--help`` stays fast even as commands grow.
"""

from __future__ import annotations

import typer
from rich.console import Console

from . import __version__
from .commands import dev, gen_keys, init, seed

console = Console()

app = typer.Typer(
    name="lvt-cert",
    help="LUONVUITUOI-CERT scaffolder — create, configure, and run certificate portals.",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(init.app, name="init")
app.add_typer(gen_keys.app, name="gen-keys")
app.add_typer(seed.app, name="seed")
app.add_typer(dev.app, name="dev")


@app.callback(invoke_without_command=True)
def _root(version: bool = typer.Option(False, "--version", "-V", help="Show version and exit.")) -> None:
    if version:
        console.print(f"lvt-cert [bold cyan]{__version__}[/]")
        raise typer.Exit()

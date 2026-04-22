"""Entry point for the ``lvt-cert`` / ``luonvuitoi-cert`` console script.

Each command module exposes a single ``run`` function; we register them as
top-level Typer commands here instead of the sub-typer pattern so positional
args (e.g. ``lvt-cert init <target>``) resolve as expected.
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

app.command(name="init", help="Scaffold a new certificate portal project.")(init.init_project)
app.command(name="gen-keys", help="Generate RSA keypair for QR signing.")(gen_keys.gen_keys)
app.command(name="seed", help="Generate fake students for local testing.")(seed.seed)
app.command(name="dev", help="Run the portal locally.")(dev.dev)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit."),
) -> None:
    if version:
        console.print(f"lvt-cert [bold cyan]{__version__}[/]")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


if __name__ == "__main__":  # pragma: no cover — hit via ``python -m luonvuitoi_cert_cli.main``
    app()

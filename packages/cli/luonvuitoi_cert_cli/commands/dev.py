"""``lvt-cert dev`` — run the portal locally under Flask.

Reads ``cert.config.json`` from the current directory, builds the Flask app
from :mod:`luonvuitoi_cert_cli.server`, and serves it. Not for production;
Vercel handlers (Phase 15) cover that.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Run the portal locally.")
console = Console()


@app.callback(invoke_without_command=True)
def dev(
    port: int = typer.Option(5000, "--port", "-p", min=1, max=65_535, help="Port to bind."),
    host: str = typer.Option("127.0.0.1", help="Host to bind."),
    config_path: Path = typer.Option(Path("cert.config.json"), "--config", "-c"),
    project_root: Path = typer.Option(Path.cwd(), "--root", help="Project root (config + templates + data)."),
    debug: bool = typer.Option(False, "--debug", help="Enable Flask debug mode."),
) -> None:
    try:
        from luonvuitoi_cert_cli.server import build_app
    except ImportError as e:
        console.print(
            f"[red]ERR[/] Flask isn't installed: {e}\n  run [cyan]pip install 'luonvuitoi-cert-cli[dev]'[/]"
        )
        raise typer.Exit(code=1) from e

    config_path = config_path.expanduser().resolve()
    project_root = project_root.expanduser().resolve()
    if not config_path.exists():
        console.print(f"[red]ERR[/] config not found: {config_path}")
        raise typer.Exit(code=1)

    app_instance = build_app(config_path, project_root)
    console.print(f"[green]OK[/] dev server at [cyan]http://{host}:{port}[/]")
    console.print(f"  config: {config_path}")
    console.print(f"  root:   {project_root}")
    app_instance.run(host=host, port=port, debug=debug, use_reloader=debug)

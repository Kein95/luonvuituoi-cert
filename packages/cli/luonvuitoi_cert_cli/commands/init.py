"""``lvt-cert init`` — scaffold a new certificate portal project.

Copies the packaged ``scaffolds/default/`` tree into ``<target>`` and
renders ``.j2`` templates with the answers from an interactive Typer
prompt (or defaults when ``--non-interactive`` is passed).

Design intent:
- Idempotent failure mode: bail before writing anything if the target is
  non-empty.
- No network calls: the skeleton is bundled inside the wheel and read via
  :mod:`importlib.resources`.
- The rendered ``cert.config.json`` is immediately round-tripped through
  :class:`CertConfig` so typos in the prompt can't produce an invalid
  project.
"""

from __future__ import annotations

import re
import shutil
from importlib import resources
from pathlib import Path

import typer
from jinja2 import Environment, StrictUndefined
from rich.console import Console

app = typer.Typer(help="Scaffold a new certificate portal project.")
console = Console()

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_SCAFFOLD_PACKAGE = "luonvuitoi_cert_cli.scaffolds.default"


def _slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()
    return s or "portal"


def _iter_scaffold_files():  # type: ignore[no-untyped-def]
    """Yield ``(relative_path, Traversable)`` pairs for every file in the scaffold."""
    root = resources.files(_SCAFFOLD_PACKAGE)

    def walk(node, prefix):  # type: ignore[no-untyped-def]
        for child in node.iterdir():
            if child.is_dir():
                yield from walk(child, prefix + (child.name,))
            else:
                yield ("/".join(prefix + (child.name,)), child)

    yield from walk(root, ())


def _render_context(name: str, slug: str, locale: str) -> dict[str, str]:
    return {"project_name": name, "project_slug": slug, "project_locale": locale}


def _validate_slug_or_exit(slug: str) -> None:
    if not _SLUG_RE.match(slug):
        console.print(
            f"[red]ERR[/] slug {slug!r} must be lowercase kebab-case (e.g. ``demo-academy``)."
        )
        raise typer.Exit(code=2)


@app.callback(invoke_without_command=True)
def init_project(
    target: Path = typer.Argument(..., help="Destination directory for the new project."),
    name: str | None = typer.Option(None, "--name", help="Project display name."),
    slug: str | None = typer.Option(None, "--slug", help="URL-safe slug (lowercase kebab-case)."),
    locale: str = typer.Option("en", "--locale", help="Default UI locale (en | vi)."),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Skip prompts; rely on --name / --slug / --locale."
    ),
) -> None:
    target = target.expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        console.print(f"[red]ERR[/] {target} exists and is not empty.")
        raise typer.Exit(code=1)

    if not non_interactive:
        name = name or typer.prompt("Project display name", default="DEMO ACADEMY")
        default_slug = _slugify(name)
        slug = slug or typer.prompt("URL slug (lowercase kebab-case)", default=default_slug)
        locale = typer.prompt("Default locale", default=locale)
    else:
        name = name or "DEMO ACADEMY"
        slug = slug or _slugify(name)

    _validate_slug_or_exit(slug)
    if locale not in ("en", "vi"):
        console.print(f"[red]ERR[/] locale must be 'en' or 'vi'; got {locale!r}.")
        raise typer.Exit(code=2)

    target.mkdir(parents=True, exist_ok=True)
    ctx = _render_context(name, slug, locale)
    env = Environment(undefined=StrictUndefined, keep_trailing_newline=True)

    for relative, source in _iter_scaffold_files():
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if relative.endswith(".j2"):
            rendered = env.from_string(source.read_text(encoding="utf-8")).render(ctx)
            dest.with_suffix("").write_text(rendered, encoding="utf-8")
        else:
            with source.open("rb") as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)

    # Round-trip the rendered config through the validator so typos fail loud.
    from luonvuitoi_cert.config import load_config

    cfg_path = target / "cert.config.json"
    try:
        load_config(cfg_path)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]ERR[/] rendered config failed validation: {e}")
        raise typer.Exit(code=3) from e

    console.print(f"[green]OK[/] scaffolded {name!r} into {target}")
    console.print("  next: [cyan]cd[/] into the project, [cyan]pip install -r requirements.txt[/],")
    console.print("        then [cyan]lvt-cert seed[/] and [cyan]lvt-cert dev[/]")

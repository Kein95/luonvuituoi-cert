"""``lvt-cert seed`` — generate fake students for local testing.

Reads ``cert.config.json`` from the current directory, invents ``--count``
students with Faker, and writes them to ``data/students.xlsx`` (or a custom
path) using the config's ``data_mapping`` column names so ingest works
without further remapping. Not intended for production data.
"""

from __future__ import annotations

import random
import secrets
from datetime import date, timedelta
from pathlib import Path

import typer
from faker import Faker
from openpyxl import Workbook
from rich.console import Console

app = typer.Typer(help="Generate fake students for local testing.")
console = Console()


def _random_dob(rng: random.Random) -> str:
    """Return a plausible school-age DOB (ages 6-18)."""
    today = date.today()
    years = rng.randint(6, 18)
    days = rng.randint(0, 365)
    dob = today - timedelta(days=years * 365 + days)
    return dob.strftime("%d-%m-%Y")


def _random_result(choices: list[str], rng: random.Random) -> str:
    return rng.choice(choices) if choices else ""


@app.callback(invoke_without_command=True)
def seed(
    count: int = typer.Option(10, "--count", "-n", min=1, max=10_000, help="Number of fake students."),
    locale: str = typer.Option("en_US", help="Faker locale (e.g., en_US, vi_VN)."),
    output: Path = typer.Option(Path("data/students.xlsx"), "--output", "-o", help="Excel output path."),
    config_path: Path = typer.Option(Path("cert.config.json"), "--config", "-c"),
    seed_value: int | None = typer.Option(None, "--seed", help="Deterministic seed for reproducible output."),
) -> None:
    from luonvuitoi_cert.config import load_config

    try:
        config = load_config(config_path)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]ERR[/] can't load config {config_path}: {e}")
        raise typer.Exit(code=1) from e

    rng = random.Random(seed_value) if seed_value is not None else random.Random(secrets.randbits(64))
    fake = Faker(locale)
    if seed_value is not None:
        Faker.seed(seed_value)

    m = config.data_mapping
    columns: list[str] = [m.sbd_col, m.name_col]
    if m.dob_col:
        columns.append(m.dob_col)
    if m.school_col:
        columns.append(m.school_col)
    if m.grade_col:
        columns.append(m.grade_col)
    if m.phone_col:
        columns.append(m.phone_col)
    columns.extend(m.extra_cols)
    for subj in config.subjects:
        columns.append(subj.db_col)

    wb = Workbook()
    ws = wb.active
    ws.append(columns)
    result_choices_by_subject = {s.code: list(config.results.get(s.code, {}).keys()) for s in config.subjects}

    for i in range(count):
        row: list[str] = [str(100_000 + i)]  # sbd
        row.append(fake.name())
        if m.dob_col:
            row.append(_random_dob(rng))
        if m.school_col:
            row.append(fake.company() + " School")
        if m.grade_col:
            row.append(str(rng.randint(1, 12)))
        if m.phone_col:
            row.append(fake.msisdn()[-10:])
        for _col in m.extra_cols:
            row.append(fake.city())
        for subj in config.subjects:
            row.append(_random_result(result_choices_by_subject[subj.code], rng))
        ws.append(row)

    out = output.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    console.print(f"[green]OK[/] wrote {count} fake students -> {out}")

"""Derive a SQLite schema from :class:`CertConfig`.

One table per round (name = ``round.table``). Columns:
- ``sbd`` — primary key, TEXT, named after ``data_mapping.sbd_col``
- Core optional columns: ``name``, ``dob``, ``school``, ``grade``, ``phone``
  (included only if declared in ``data_mapping``)
- ``extra_cols`` — user-declared flex columns
- One result column per subject, named after ``subject.db_col``

All columns are TEXT — SQLite is dynamically typed and students' raw Excel
values can be mixed numeric/string without penalty. Handlers cast when needed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.config.models import _SQL_IDENT


class SchemaError(Exception):
    """Raised when the schema derived from a config is malformed or has column collisions."""


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    name: str
    is_primary: bool = False

    def sql(self) -> str:
        pk = " PRIMARY KEY" if self.is_primary else ""
        return f'"{self.name}" TEXT{pk}'


@dataclass(frozen=True, slots=True)
class TableSpec:
    name: str
    columns: tuple[ColumnSpec, ...]

    def create_sql(self) -> str:
        cols = ",\n  ".join(c.sql() for c in self.columns)
        return f'CREATE TABLE IF NOT EXISTS "{self.name}" (\n  {cols}\n);'


def _validate_ident(name: str, field: str) -> str:
    if not _SQL_IDENT.match(name):
        raise SchemaError(f"{field} is not a valid SQL identifier: {name!r}")
    return name


def _collect_columns(config: CertConfig) -> list[ColumnSpec]:
    """Build the ordered column list shared by every round table."""
    m = config.data_mapping
    seen: dict[str, ColumnSpec] = {}

    def add(col: str, *, primary: bool = False) -> None:
        _validate_ident(col, "column")
        if col in seen:
            if primary and not seen[col].is_primary:
                seen[col] = ColumnSpec(col, is_primary=True)
            return
        seen[col] = ColumnSpec(col, is_primary=primary)

    add(m.sbd_col, primary=True)
    add(m.name_col)
    for col in (m.dob_col, m.school_col, m.grade_col, m.phone_col):
        if col:
            add(col)
    for col in m.extra_cols:
        add(col)
    for subj in config.subjects:
        add(subj.db_col)
    return list(seen.values())


def build_schema(config: CertConfig) -> list[TableSpec]:
    """Return one :class:`TableSpec` per round, sharing the same column set."""
    if not config.rounds:
        raise SchemaError("config has no rounds; cannot build schema")
    columns = tuple(_collect_columns(config))
    tables: list[TableSpec] = []
    seen_names: set[str] = set()
    for r in config.rounds:
        table_name = _validate_ident(r.table, f"rounds[{r.id!r}].table")
        if table_name in seen_names:
            raise SchemaError(f"two rounds share the same table name: {table_name!r}")
        seen_names.add(table_name)
        tables.append(TableSpec(name=table_name, columns=columns))
    return tables


def render_create_sql(tables: Iterable[TableSpec]) -> str:
    """Combine multiple CREATE TABLE statements into one migration script."""
    return "\n\n".join(t.create_sql() for t in tables) + "\n"

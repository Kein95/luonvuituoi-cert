"""Shared types for the ingest pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


class IngestError(Exception):
    """Raised when a source file is malformed beyond per-row recovery."""


@dataclass(slots=True)
class IngestResult:
    """Summary of a single ingest run. Non-fatal issues are recorded, not raised."""

    rows_inserted: int = 0
    rows_skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return self.rows_inserted + self.rows_skipped

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def summary(self) -> str:
        return f"inserted={self.rows_inserted} skipped={self.rows_skipped} warnings={len(self.warnings)}"

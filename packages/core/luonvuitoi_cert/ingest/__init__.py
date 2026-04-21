"""Ingest student records from Excel / CSV / JSON into the derived SQLite DB.

Each reader (:func:`read_excel`, :func:`read_csv`, :func:`read_json`) returns
a list of raw row dicts keyed by source column name. :func:`ingest_rows`
takes those rows, keeps only the columns the config declares, and inserts
them into the round's table using parameterized queries.

Google Sheets reader is deferred to a later phase (needs OAuth / service
account machinery).
"""

from luonvuitoi_cert.ingest.base import IngestError, IngestResult
from luonvuitoi_cert.ingest.csv_reader import read_csv
from luonvuitoi_cert.ingest.excel_reader import read_excel
from luonvuitoi_cert.ingest.json_reader import read_json
from luonvuitoi_cert.ingest.orchestrator import ingest_rows

__all__ = [
    "IngestError",
    "IngestResult",
    "ingest_rows",
    "read_csv",
    "read_excel",
    "read_json",
]

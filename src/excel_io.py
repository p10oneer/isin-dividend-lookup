"""Read ISIN uploads and write result workbooks."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pandas as pd

from src.isin_validate import is_header_cell, normalize_isin

RESULT_COLUMNS = [
    "ISIN",
    "Name",
    "Yahoo ticker",
    "Dividend",
    "Currency",
    "Ex-date",
    "Pay-date",
    "Source",
    "Status",
    "Lookup time",
]

DISCLAIMER = (
    "Источники: OpenFIGI (сопоставление ISIN), Yahoo Finance и Nasdaq (дивиденды США). "
    "Это публичные неофициальные источники, а не замена Bloomberg, Refinitiv "
    "или внутреннему golden source. Pay-date пустой, если источник его не даёт."
)


def parse_isins_from_excel(data: bytes) -> list[str]:
    df = pd.read_excel(BytesIO(data), sheet_name=0, header=None, dtype=str)
    if df.empty:
        return []
    series = df.iloc[:, 0]
    values = [normalize_isin(v) for v in series.tolist()]
    if values and is_header_cell(values[0]):
        values = values[1:]
    return [v for v in values if v]


def parse_isins_from_text(text: str) -> list[str]:
    rows: list[str] = []
    for line in (text or "").splitlines():
        for part in line.replace(";", ",").split(","):
            isin = normalize_isin(part)
            if isin and not is_header_cell(isin):
                rows.append(isin)
    return rows


def template_excel_bytes() -> bytes:
    buf = BytesIO()
    pd.DataFrame({"ISIN": []}).to_excel(buf, index=False, sheet_name="Div")
    return buf.getvalue()


def result_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    export = df.reindex(columns=RESULT_COLUMNS)
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        export.to_excel(writer, index=False, sheet_name="Dividends")
    return buf.getvalue()


def result_csv_bytes(df: pd.DataFrame) -> bytes:
    export = df.reindex(columns=RESULT_COLUMNS)
    return export.to_csv(index=False).encode("utf-8-sig")


def timestamped_basename(now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return f"dividends_{stamp}"

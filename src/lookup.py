"""Orchestrate ISIN validation, mapping fallbacks, and dividend lookup."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

import pandas as pd

from src.excel_io import RESULT_COLUMNS
from src.isin_validate import classify_isin, corrected_isin, us_cusip
from src.yahoo_div import candidate_tickers, fetch_last_dividend, search_yahoo_isin

ProgressFn = Callable[[int, int, str], None]
FetchFn = Callable[[str], dict[str, Any]]
SearchFn = Callable[[str], dict[str, str | None]]


def extra_mapping_isins(isins: list[str]) -> list[str]:
    """Original ISINs plus checksum-corrected variants for OpenFIGI."""
    out: list[str] = []
    seen: set[str] = set()
    for isin in isins:
        for candidate in (isin, corrected_isin(isin)):
            if candidate and candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
    return out


def lookup_dividends(
    isins: list[str],
    figi_map: dict[str, dict[str, Any]],
    *,
    fetch: FetchFn = fetch_last_dividend,
    search: SearchFn = search_yahoo_isin,
    on_progress: ProgressFn | None = None,
    pause_s: float = 0.2,
) -> pd.DataFrame:
    import time

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows: list[dict[str, Any]] = []
    total = len(isins)

    for i, isin in enumerate(isins, start=1):
        kind = classify_isin(isin)
        if on_progress:
            on_progress(i, total, isin)

        if kind == "invalid":
            rows.append(_row(isin, now, status="Некорректный ISIN"))
            continue

        fixed = corrected_isin(isin)
        mapped = figi_map.get(isin) or {}
        if not mapped.get("listings"):
            mapped = figi_map.get(fixed or "") or mapped

        name = mapped.get("name")
        tickers = candidate_tickers(mapped.get("listings") or [])

        if kind == "ok":
            tickers.append(isin)

        if not mapped.get("listings"):
            queries = [isin]
            if fixed and fixed not in queries:
                queries.append(fixed)
            cusip = us_cusip(isin)
            if cusip:
                queries.append(cusip)
            for query in queries:
                hit = search(query) or {}
                if hit.get("name") and not name:
                    name = hit["name"]
                if hit.get("ticker"):
                    tickers.append(str(hit["ticker"]))

        # Dedupe, keep order
        seen: set[str] = set()
        unique_tickers: list[str] = []
        for symbol in tickers:
            if symbol and symbol not in seen:
                seen.add(symbol)
                unique_tickers.append(symbol)

        if not unique_tickers:
            if kind == "checksum":
                status = "Не найден: ошибка check digit ISIN (возможна опечатка)"
            else:
                status = "Не сопоставлен"
            rows.append(_row(isin, now, name=name, status=status))
            continue

        result: dict[str, Any] | None = None
        used = unique_tickers[0]
        for symbol in unique_tickers:
            used = symbol
            if on_progress:
                on_progress(i, total, f"{isin} → {symbol}")
            result = fetch(symbol)
            status = result.get("status")
            if status == "OK" or status == "No dividend history":
                break
        assert result is not None

        status = str(result.get("status") or "Ошибка запроса")
        if kind == "checksum" and status == "OK":
            status = "OK (ошибка check digit ISIN)"
        elif kind == "checksum" and status == "No dividend history":
            status = "No dividend history (ошибка check digit ISIN)"

        display_ticker = result.get("ticker") or used
        if display_ticker == isin or (fixed and display_ticker == fixed):
            # Prefer a market ticker if we also found one
            for symbol in unique_tickers:
                if symbol not in {isin, fixed}:
                    display_ticker = symbol
                    break

        rows.append(
            _row(
                isin,
                now,
                name=name,
                ticker=display_ticker,
                dividend=result.get("dividend"),
                currency=result.get("currency"),
                ex_date=result.get("ex_date"),
                pay_date=result.get("pay_date"),
                status=status,
                source=result.get("source"),
            )
        )
        if pause_s:
            time.sleep(pause_s)

    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


def _row(
    isin: str,
    lookup_time: str,
    *,
    name: str | None = None,
    ticker: str | None = None,
    dividend: float | None = None,
    currency: str | None = None,
    ex_date: str | None = None,
    pay_date: str | None = None,
    status: str = "",
    source: str | None = None,
) -> dict[str, Any]:
    return {
        "ISIN": isin,
        "Name": name,
        "Yahoo ticker": ticker,
        "Dividend": dividend,
        "Currency": currency,
        "Ex-date": ex_date,
        "Pay-date": pay_date,
        "Source": source,
        "Status": status,
        "Lookup time": lookup_time,
    }


def summarize(df: pd.DataFrame) -> dict[str, int]:
    if df.empty:
        return {"total": 0, "ok": 0, "no_div": 0, "failed": 0}
    status = df["Status"].astype(str)
    ok = int(status.str.startswith("OK").sum())
    no_div = int(status.str.startswith("No dividend history").sum())
    failed = int(len(df) - ok - no_div)
    return {"total": len(df), "ok": ok, "no_div": no_div, "failed": failed}

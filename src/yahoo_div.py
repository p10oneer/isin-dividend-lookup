"""Last paid cash dividend from Yahoo Finance."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import yfinance as yf

from src.openfigi import yahoo_symbol
from src.nasdaq_div import fetch_nasdaq_dividend


def _as_date(value: Any) -> date | None:
    if value is None or (isinstance(value, float) and value != value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().date()
        except Exception:
            return None
    if isinstance(value, (int, float)):
        try:
            ts = float(value)
            if ts > 10_000_000_000:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc).date()
        except (OSError, OverflowError, ValueError):
            return None
    return None


def _fmt(d: date | None) -> str | None:
    return d.isoformat() if d else None


def fetch_last_dividend(ticker: str) -> dict[str, Any]:
    """Return last cash dividend fields or a status error. Never invents an amount."""
    last_error = "Ошибка запроса"
    for attempt in range(3):
        try:
            t = yf.Ticker(ticker)
            divs = t.dividends
            currency = None
            try:
                currency = t.fast_info.get("currency")
            except Exception:
                currency = None

            info: dict[str, Any] = {}
            amount = None
            ex_date = None
            if divs is not None and len(divs) > 0:
                amount = float(divs.iloc[-1])
                ex_date = _as_date(divs.index[-1])
            else:
                try:
                    info = t.get_info() or {}
                except Exception:
                    info = {}
                if not currency:
                    currency = info.get("currency")
                last_val = info.get("lastDividendValue")
                last_dt = _as_date(info.get("lastDividendDate") or info.get("exDividendDate"))
                if last_val is not None:
                    amount = float(last_val)
                    ex_date = last_dt

            if amount is None:
                nasdaq = fetch_nasdaq_dividend(ticker)
                if nasdaq.get("status") == "OK":
                    return nasdaq
                return {
                    "ticker": ticker,
                    "dividend": None,
                    "currency": currency,
                    "ex_date": None,
                    "pay_date": None,
                    "status": "No dividend history",
                    "source": None,
                }

            if not info:
                try:
                    info = t.get_info() or {}
                except Exception:
                    info = {}
            if not currency:
                currency = info.get("currency")
            pay = _as_date(info.get("dividendDate"))
            last_div_date = _as_date(info.get("lastDividendDate"))
            # Yahoo dividendDate is often the next payment; keep it only if it
            # sits after the last ex-date and within ~120 days.
            pay_date = None
            if pay and ex_date and ex_date <= pay <= ex_date + timedelta(days=120):
                pay_date = pay
            elif last_div_date and ex_date and last_div_date != ex_date:
                if last_div_date >= ex_date:
                    pay_date = last_div_date

            return {
                "ticker": ticker,
                "dividend": amount,
                "currency": currency,
                "ex_date": _fmt(ex_date),
                "pay_date": _fmt(pay_date),
                "status": "OK",
                "source": "Yahoo Finance",
            }
        except ValueError as exc:
            if "ISIN" in str(exc).upper():
                return {
                    "ticker": ticker,
                    "dividend": None,
                    "currency": None,
                    "ex_date": None,
                    "pay_date": None,
                    "status": "Нет ticker",
                    "source": None,
                }
            last_error = "Ошибка запроса"
            time.sleep(1.2 * (attempt + 1))
        except Exception as exc:
            last_error = "Ошибка запроса"
            _ = exc
            time.sleep(1.2 * (attempt + 1))
    return {
        "ticker": ticker,
        "dividend": None,
        "currency": None,
        "ex_date": None,
        "pay_date": None,
        "status": last_error,
        "source": None,
    }


def search_yahoo_isin(query: str) -> dict[str, str | None]:
    """Resolve an ISIN or CUSIP to a Yahoo symbol via Yahoo search."""
    q = (query or "").strip()
    if not q:
        return {"ticker": None, "name": None}
    try:
        result = yf.Search(q)
        quotes = list(getattr(result, "quotes", None) or [])
    except Exception:
        return {"ticker": None, "name": None}
    if not quotes:
        return {"ticker": None, "name": None}

    def rank(item: dict[str, Any]) -> tuple[int, float]:
        qtype = str(item.get("quoteType") or item.get("typeDisp") or "").upper()
        preferred = 0 if qtype in {"EQUITY", "ETF", "MUTUALFUND", "INDEX"} else 1
        return (preferred, -float(item.get("score") or 0))

    quotes.sort(key=rank)
    top = quotes[0]
    symbol = top.get("symbol")
    name = top.get("longname") or top.get("shortname")
    return {"ticker": str(symbol) if symbol else None, "name": str(name) if name else None}


def candidate_tickers(listings: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for row in listings:
        symbol = yahoo_symbol(str(row.get("ticker") or ""), row.get("exchCode"))
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out

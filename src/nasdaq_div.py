"""US dividend history from Nasdaq's public quote API (no key)."""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

import requests
import urllib3
from requests.exceptions import SSLError

_AMOUNT = re.compile(r"[-+]?\d[\d,]*\.?\d*")


def _parse_amount(text: object) -> float | None:
    if text is None:
        return None
    m = _AMOUNT.search(str(text).replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _parse_date(text: object) -> str | None:
    if not text or str(text).strip() in {"", "N/A", "n/a"}:
        return None
    raw = str(text).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _get(symbol: str, assetclass: str, verify: bool) -> dict[str, Any] | None:
    resp = requests.get(
        f"https://api.nasdaq.com/api/quote/{symbol}/dividends",
        params={"assetclass": assetclass},
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
        timeout=25,
        verify=verify,
    )
    if resp.status_code != 200:
        return None
    payload = resp.json()
    data = (payload or {}).get("data") or {}
    rows = ((data.get("dividends") or {}).get("rows")) or []
    return rows[0] if rows else None


def fetch_nasdaq_dividend(ticker: str) -> dict[str, Any]:
    """Last cash dividend for a US symbol. Blank result if Nasdaq has none."""
    symbol = (ticker or "").split(".")[0].split(":")[-1].strip().upper()
    if not symbol or len(symbol) > 10:
        return {"status": "No dividend history"}

    use_verify = True
    last_error = "Ошибка запроса"
    for attempt in range(3):
        try:
            row = None
            for assetclass in ("stocks", "etf"):
                row = _get(symbol, assetclass, use_verify)
                if row:
                    break
            if not row:
                return {
                    "ticker": symbol,
                    "dividend": None,
                    "currency": None,
                    "ex_date": None,
                    "pay_date": None,
                    "status": "No dividend history",
                    "source": None,
                }
            dtype = str(row.get("type") or "").lower()
            if dtype and dtype not in {"cash", "cash dividend", ""}:
                return {
                    "ticker": symbol,
                    "dividend": None,
                    "currency": row.get("currency") or "USD",
                    "ex_date": None,
                    "pay_date": None,
                    "status": "No dividend history",
                    "source": None,
                }
            amount = _parse_amount(row.get("amount"))
            if amount is None:
                return {"status": "No dividend history", "ticker": symbol}
            return {
                "ticker": symbol,
                "dividend": amount,
                "currency": row.get("currency") or "USD",
                "ex_date": _parse_date(row.get("exOrEffDate")),
                "pay_date": _parse_date(row.get("paymentDate")),
                "status": "OK",
                "source": "Nasdaq",
            }
        except SSLError:
            if use_verify:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                use_verify = False
                continue
            last_error = "Ошибка запроса"
            time.sleep(1.0 * (attempt + 1))
        except Exception:
            last_error = "Ошибка запроса"
            time.sleep(1.0 * (attempt + 1))
    return {
        "ticker": symbol,
        "dividend": None,
        "currency": None,
        "ex_date": None,
        "pay_date": None,
        "status": last_error,
        "source": None,
    }

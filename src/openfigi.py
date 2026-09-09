"""OpenFIGI ISIN → listing mapping and Yahoo ticker construction."""

from __future__ import annotations

import time
from typing import Any

import requests

import urllib3
from requests.exceptions import SSLError

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"

_used_insecure_ssl = False


def used_insecure_ssl() -> bool:
    return _used_insecure_ssl


# OpenFIGI exchCode → Yahoo Finance suffix
_YAHOO_SUFFIX: dict[str, str] = {
    "UN": "",
    "UW": "",
    "UA": "",
    "UP": "",
    "UQ": "",
    "UV": "",
    "US": "",
    "UM": "",
    "UR": "",
    "UT": "",
    "LN": ".L",
    "L": ".L",
    "GY": ".DE",
    "GF": ".F",
    "GM": ".ME",
    "GT": ".MU",
    "GS": ".SG",
    "GH": ".HA",
    "FP": ".PA",
    "NA": ".AS",
    "BB": ".BR",
    "IM": ".MI",
    "SM": ".MC",
    "PL": ".LS",
    "DC": ".CO",
    "SS": ".ST",
    "FH": ".HE",
    "NO": ".OL",
    "SW": ".SW",
    "VX": ".SW",
    "S": ".SW",
    "HK": ".HK",
    "JT": ".T",
    "JP": ".T",
    "T": ".T",
    "AU": ".AX",
    "AX": ".AX",
    "NZ": ".NZ",
    "SP": ".SI",
    "KS": ".KS",
    "KQ": ".KQ",
    "TT": ".TW",
    "TWO": ".TWO",
    "IB": ".BO",
    "IN": ".NS",
    "IS": ".NS",
    "TO": ".TO",
    "CN": ".TO",
    "CV": ".V",
    "CNQ": ".V",
    "SE": ".SA",
    "MM": ".MX",
    "JO": ".JO",
    "SJ": ".JO",
    "JK": ".JK",
    "IJ": ".JK",
    "TB": ".BK",
    "PM": ".PS",
    "TI": ".IS",
    "AT": ".AT",
    "AV": ".VI",
    "PW": ".WA",
    "IR": ".IR",
}

_PREFERRED_TYPES = {
    "common stock",
    "reit",
    "etp",
    "etf",
    "mutual fund",
    "preferred stock",
    "adr",
    "gdr",
    "nyrs",
    "closed-end fund",
    "unit",
}

_US_EXCH = {"UN", "UW", "UA", "UP", "UQ", "UV", "US", "UM", "UR", "UT"}


def _headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key.strip()
    return headers


def yahoo_symbol(ticker: str, exch_code: str | None) -> str | None:
    if not ticker:
        return None
    symbol = str(ticker).strip().upper().replace(" ", "-")
    suffix = _YAHOO_SUFFIX.get((exch_code or "").strip().upper())
    if suffix is None:
        # Unknown exchange: still try bare ticker (often US)
        return symbol
    return f"{symbol}{suffix}"


def _rank(item: dict[str, Any]) -> tuple[int, int, str]:
    stype = str(item.get("securityType") or item.get("securityType2") or "").lower()
    exch = str(item.get("exchCode") or "").upper()
    preferred = 0 if stype in _PREFERRED_TYPES else 1
    us = 0 if exch in _US_EXCH else 1
    return (preferred, us, exch)


def pick_listings(data: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not data:
        return []
    usable = [row for row in data if row.get("ticker")]
    usable.sort(key=_rank)
    return usable


def _post_batch(
    jobs: list[dict[str, str]],
    api_key: str | None,
    verify: bool = True,
) -> list[dict[str, Any]]:
    global _used_insecure_ssl
    last_error: Exception | None = None
    use_verify = verify
    for attempt in range(4):
        try:
            resp = requests.post(
                OPENFIGI_URL,
                json=jobs,
                headers=_headers(api_key),
                timeout=30,
                verify=use_verify,
            )
            if resp.status_code in {429, 500, 502, 503, 504}:
                time.sleep(1.5 * (attempt + 1))
                last_error = RuntimeError(f"OpenFIGI HTTP {resp.status_code}")
                continue
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, list):
                raise RuntimeError("Unexpected OpenFIGI response")
            return payload
        except SSLError as exc:
            last_error = exc
            if use_verify:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                use_verify = False
                _used_insecure_ssl = True
                continue
            time.sleep(1.5 * (attempt + 1))
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"OpenFIGI request failed: {last_error}")


def map_isins(
    isins: list[str],
    api_key: str | None = None,
    *,
    ssl_verify: bool = True,
) -> dict[str, dict[str, Any]]:
    """Map unique ISINs to listing metadata. Values are {name, listings, error}."""
    global _used_insecure_ssl
    _used_insecure_ssl = False
    unique: list[str] = []
    seen: set[str] = set()
    for isin in isins:
        if isin not in seen:
            seen.add(isin)
            unique.append(isin)

    batch_size = 25 if (api_key and api_key.strip()) else 10
    out: dict[str, dict[str, Any]] = {}

    for i in range(0, len(unique), batch_size):
        chunk = unique[i : i + batch_size]
        jobs = [{"idType": "ID_ISIN", "idValue": isin} for isin in chunk]
        results = _post_batch(jobs, api_key, verify=ssl_verify)
        for isin, result in zip(chunk, results):
            if not isinstance(result, dict):
                out[isin] = {"name": None, "listings": [], "error": "Not mapped"}
                continue
            if result.get("error"):
                out[isin] = {"name": None, "listings": [], "error": "Not mapped"}
                continue
            listings = pick_listings(result.get("data") or [])
            name = listings[0].get("name") if listings else None
            out[isin] = {"name": name, "listings": listings, "error": None if listings else "Not mapped"}
        if i + batch_size < len(unique):
            time.sleep(0.4)

    return out

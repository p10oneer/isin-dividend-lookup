# ISIN Dividend Lookup

Streamlit tool for back-office: upload a list of ISINs, map them through OpenFIGI, fetch the **last paid cash dividend per share** from Yahoo Finance, and download a timestamped Excel/CSV file.

## Streamlit Community Cloud

Main file: `app.py`. After the repo is on GitHub, deploy from [share.streamlit.io](https://share.streamlit.io) (Connect GitHub → this repository → Deploy).

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

No API key is required in the app. End users only upload a file and click Lookup.

IT optional: set environment variable `OPENFIGI_API_KEY` (free key from [OpenFIGI](https://www.openfigi.com/api)) if large files get rate-limited. The key is not shown in the UI.

## Input

First sheet, first column. A header such as `ISIN` is skipped. Extra columns are ignored. You can also paste ISINs (one per line).

Example layout (see `Div_test.xlsx`):

| ISIN         |
| ------------ |
| US21037T1097 |
| US4642872265 |

## Output

Columns: ISIN, Name, Yahoo ticker, Dividend, Currency, Ex-date, Pay-date, Source, Status, Lookup time.

Downloads are named `dividends_YYYYMMDD_HHMMSS.xlsx` / `.csv` (new timestamp every click).

Lookups try, in order: OpenFIGI → Yahoo by ISIN → Yahoo search → Nasdaq (US). No extra keys in the UI.

Status values include `OK`, `OK (checksum mismatch)`, `Invalid ISIN`, `Invalid ISIN check digit - not found (possible typo)`, `Not mapped`, `No Yahoo ticker`, `No dividend history`, `Lookup failed`.

## Limits

- Best for listed equities and ETFs. Bonds and private names often have no public dividend series.
- Public sources may omit pay-dates, delay updates, or rate-limit.
- This is **not** a substitute for Bloomberg, Refinitiv, or an internal golden source.

## License / data

OpenFIGI, Yahoo Finance, and Nasdaq terms apply to any data you retrieve.

"""Streamlit app: last cash dividend lookup by ISIN."""

from __future__ import annotations

import html
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from src.excel_io import (
    parse_isins_from_excel,
    parse_isins_from_text,
    result_csv_bytes,
    result_excel_bytes,
    template_excel_bytes,
    timestamped_basename,
)
from src.lookup import extra_mapping_isins, lookup_dividends, summarize
from src.openfigi import map_isins, used_insecure_ssl
from src.yahoo_div import fetch_last_dividend, search_yahoo_isin

ROOT = Path(__file__).resolve().parent
LOGO = ROOT / "assets" / "brand" / "logo-green.svg"
MARK = ROOT / "assets" / "brand" / "mark-green.svg"
CSS = ROOT / "assets" / "brand" / "app.css"

FOREST = "#0B534F"
LARGE_BATCH = 150

TABLE_COLUMNS = [
    ("ISIN", "ISIN"),
    ("Name", "Название"),
    ("Yahoo ticker", "Ticker"),
    ("Dividend", "Dividend"),
    ("Currency", "Currency"),
    ("Ex-date", "Ex-date"),
    ("Pay-date", "Pay-date"),
    ("Source", "Source"),
    ("Status", "Status"),
    ("Lookup time", "Время запроса"),
]


def _row_class(status: str) -> str:
    if status.startswith("OK"):
        return "row-ok"
    if status.startswith("No dividend history"):
        return "row-nodiv"
    return "row-problem"


def _cell_text(value: object, column: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if column == "Dividend" and isinstance(value, (int, float)):
        return f"{value:g}"
    return str(value)


def render_status_table(df: pd.DataFrame) -> str:
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in TABLE_COLUMNS)
    body_rows = []
    for _, row in df.iterrows():
        status = str(row.get("Status") or "")
        row_class = _row_class(status)
        cells = "".join(
            f"<td>{html.escape(_cell_text(row.get(col), col))}</td>" for col, _ in TABLE_COLUMNS
        )
        body_rows.append(f'<tr class="{row_class}">{cells}</tr>')
    return (
        '<div class="bcc-table-wrap"><table class="bcc-table">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


def _inject_css() -> None:
    css = CSS.read_text(encoding="utf-8") if CSS.is_file() else ""
    if css:
        st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)


st.set_page_config(
    page_title="Дивиденды по ISIN | BCC Invest",
    page_icon=str(MARK) if MARK.exists() else None,
    layout="wide",
    initial_sidebar_state="expanded",
)
_inject_css()


@st.cache_data(ttl=86400, show_spinner=False)
def cached_map_isins(isins: tuple[str, ...], api_key: str | None) -> dict:
    return map_isins(list(isins), api_key or None)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_search_isin(query: str) -> dict:
    return search_yahoo_isin(query)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_fetch_dividend(ticker: str) -> dict:
    return fetch_last_dividend(ticker)


def _init_state() -> None:
    if "results" not in st.session_state:
        st.session_state.results = None
    if "source_label" not in st.session_state:
        st.session_state.source_label = ""


def _collect_isins(uploaded, pasted: str) -> tuple[list[str], str]:
    isins: list[str] = []
    source_label = ""
    if uploaded is not None:
        try:
            isins = parse_isins_from_excel(uploaded.getvalue())
            source_label = uploaded.name
        except Exception as exc:
            st.error(f"Не удалось прочитать Excel: {exc}")
            isins = []
    if pasted.strip():
        pasted_isins = parse_isins_from_text(pasted)
        if isins:
            isins = isins + pasted_isins
            source_label = f"{source_label} + вставка" if source_label else "вставка"
        else:
            isins = pasted_isins
            source_label = "вставка"
    return isins, source_label


def main() -> None:
    _init_state()

    if LOGO.exists():
        st.logo(str(LOGO), icon_image=str(MARK) if MARK.exists() else str(LOGO), size="medium")
        st.image(str(LOGO), width=220)

    st.markdown(
        """
<div class="bcc-hero">
  <p class="bcc-kicker">BCC Invest · бэк-офис</p>
  <h1>Дивиденды по ISIN</h1>
  <p>Загрузите список ISIN — программа найдёт последний выплаченный cash dividend per share
  (сумма, Currency, Ex-date, Pay-date) и отдаст Excel с уникальным именем файла.</p>
</div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Как пользоваться — краткая инструкция", expanded=False):
        st.markdown(
            """
<div class="bcc-guide" style="color:#21252B;">
<p><strong>Что подготовить.</strong> Excel: первый лист, первый столбец — коды <strong>ISIN</strong>. Заголовок <code>ISIN</code> пропускается. Другие столбцы игнорируются.</p>
<ol>
<li><strong>Слева</strong> загрузите файл или вставьте ISIN (по одному в строке).</li>
<li>Проверьте сообщение, сколько кодов загружено, затем нажмите <strong>«Найти дивиденды»</strong>.</li>
<li>Дождитесь таблицы. Фильтр: Все / OK / Проблемы.</li>
<li>Скачайте <strong>Excel</strong> или <strong>CSV</strong>. Имя файла содержит дату и время, предыдущая копия не затрётся.</li>
</ol>
<p><strong>Колонки в таблице</strong> (отраслевые названия на английском): <strong>ISIN</strong>, <strong>Ticker</strong>, <strong>Dividend</strong>, <strong>Currency</strong>, <strong>Ex-date</strong>, <strong>Pay-date</strong>, <strong>Status</strong>.</p>
<p><strong>Status</strong></p>
<div class="bcc-legend">
  <span class="bcc-chip chip-ok">OK — дивиденд найден</span>
  <span class="bcc-chip chip-nodiv">No dividend history — выплат нет в источниках</span>
  <span class="bcc-chip chip-fail">Проблема — ISIN не найден или ошибка</span>
</div>
</div>
            """,
            unsafe_allow_html=True,
        )

    api_key = (os.environ.get("OPENFIGI_API_KEY") or "").strip() or None

    with st.sidebar:
        st.markdown("### Работа со списком")
        st.caption("Сначала файл или вставка ISIN, затем кнопка поиска.")
        uploaded = st.file_uploader(
            "1. Загрузить Excel с ISIN",
            type=["xlsx", "xls"],
            help="Первый лист, первый столбец. Можно скачать шаблон справа в инструкции.",
        )
        pasted = st.text_area("Или вставьте ISIN (по одному в строке)", height=120, placeholder="US0378331005")
        st.download_button(
            "Шаблон Excel (столбец ISIN)",
            data=template_excel_bytes(),
            file_name="ISIN_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="template_dl",
            use_container_width=True,
        )
        isins, source_label = _collect_isins(uploaded, pasted)
        st.markdown("**2. Найти дивиденды**")
        if isins:
            st.caption(f"Загружено ISIN: {len(isins)} ({source_label}).")
        else:
            st.caption("Файл или вставка ещё не заданы.")
        run = st.button(
            "Найти дивиденды",
            type="primary",
            disabled=not isins,
            use_container_width=True,
        )

    if not isins:
        st.markdown(
            f"""
<div class="bcc-empty">
  <p style="margin:0 0 0.35rem 0;font-weight:600;color:{FOREST};">Файлы ещё не загружены</p>
  <p style="margin:0;">Слева выберите Excel со столбцом ISIN или вставьте коды. После поиска здесь появятся
  таблица и кнопки скачивания.</p>
</div>
            """,
            unsafe_allow_html=True,
        )
        return

    if len(isins) > LARGE_BATCH:
        st.warning(f"В списке {len(isins)} ISIN. Обработка может занять несколько минут.")

    if run:
        unique = tuple(extra_mapping_isins(isins))
        progress = st.progress(0.0, text="Сопоставление ISIN…")
        status_box = st.empty()
        try:
            figi_map = cached_map_isins(unique, api_key)
            if used_insecure_ssl():
                st.warning("Сертификат источника данных не прошёл проверку в этой сети. Поиск продолжен.")
        except Exception as exc:
            progress.empty()
            st.error(f"Не удалось сопоставить ISIN. Повторите через минуту. ({exc})")
            return

        def on_progress(i: int, total: int, label: str) -> None:
            progress.progress(i / total, text=f"{i} / {total}")
            status_box.caption(label)

        df = lookup_dividends(
            isins,
            figi_map,
            fetch=cached_fetch_dividend,
            search=cached_search_isin,
            on_progress=on_progress,
        )
        progress.progress(1.0, text="Готово")
        status_box.empty()
        st.session_state.results = df
        st.session_state.source_label = source_label

    df: pd.DataFrame | None = st.session_state.results
    if df is None:
        st.info(f"Загружено ISIN: {len(isins)} ({source_label}). Нажмите «Найти дивиденды» слева.")
        return

    stats = summarize(df)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Всего", stats["total"])
    c2.metric("OK", stats["ok"])
    c3.metric("No dividend", stats["no_div"])
    c4.metric("Ошибки / прочее", stats["failed"])

    filter_choice = st.radio("Показать", ["Все", "OK", "Проблемы"], horizontal=True)
    view = df
    status = df["Status"].astype(str)
    if filter_choice == "OK":
        view = df[status.str.startswith("OK")]
    elif filter_choice == "Проблемы":
        view = df[~status.str.startswith("OK")]

    st.markdown(render_status_table(view), unsafe_allow_html=True)

    stamp = timestamped_basename(datetime.now())
    xlsx = result_excel_bytes(df)
    csv = result_csv_bytes(df)
    d1, d2 = st.columns(2)
    with d1:
        st.download_button(
            "Скачать Excel",
            data=xlsx,
            file_name=f"{stamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"xlsx_{stamp}",
            type="primary",
            use_container_width=True,
        )
    with d2:
        st.download_button(
            "Скачать CSV",
            data=csv,
            file_name=f"{stamp}.csv",
            mime="text/csv",
            key=f"csv_{stamp}",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()

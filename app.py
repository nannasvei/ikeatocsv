import csv
import io
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import pyperclip
import requests
import streamlit as st


API_PREFIX = "https://web-api.ikea.com/circular/circular-asis/api/public/offers/pl/pl/"


UNIT_ID_TO_STORE: Dict[str, Tuple[str, str]] = {
    "188": ("warszawa-janki", "warszawa+janki"),
    "203": ("gdansk", "gdańsk"),
    "204": ("krakow", "kraków"),
    "205": ("poznan", "poznań"),
    "294": ("wroclaw", "wrocław"),
    "306": ("katowice", "katowice"),
    "307": ("warszawa-targowek", "warszawa+targówek"),
    "311": ("lublin", "lublin"),
    "329": ("lodz", "łódź"),
    "429": ("bydgoszcz", "bydgoszcz"),
    "583": ("szczecin", "szczecin"),
}

CSV_COLUMNS = [
    "zdjecie",
    "nazwa",
    "opis",
    "kod_artykulu",
    "link_produktu",
    "cena_katalogowa",
    "cena_promocyjna",
    "procent_obnizki",
    "powod_obnizki_pl",
    "status",
    "link_okazji",
    "sklep",
]


@dataclass(frozen=True)
class OfferRow:
    zdjecie: str
    nazwa: str
    opis: str
    kod_artykulu: str
    link_produktu: str
    cena_katalogowa: Optional[float]
    cena_promocyjna: Optional[float]
    procent_obnizki: Optional[float]
    powod_obnizki_pl: str
    status: str
    link_okazji: str
    sklep: str


def safe_get(d: Dict[str, Any], path: str, default: Any = "") -> Any:
    cur: Any = d
    for part in path.split("."):
        if "[" in part and part.endswith("]"):
            key = part[: part.index("[")]
            idx = int(part[part.index("[") + 1 : -1])
            if not isinstance(cur, dict):
                return default
            cur = cur.get(key, [])
            if not isinstance(cur, list) or idx >= len(cur):
                return default
            cur = cur[idx]
        else:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(part, default)
    return cur


def calc_discount_percent(catalog_price: Optional[float], promo_price: Optional[float]) -> Optional[float]:
    if catalog_price is None or promo_price is None:
        return None
    try:
        catalog = float(catalog_price)
        promo = float(promo_price)
    except (TypeError, ValueError):
        return None
    if catalog <= 0:
        return None
    return round(((catalog - promo) / catalog) * 100.0, 2)


def store_from_unit_id(unit_id: Any) -> Tuple[str, str]:
    unit_str = str(unit_id) if unit_id is not None else ""
    return UNIT_ID_TO_STORE.get(unit_str, ("", ""))


def fetch_offer(tag_id: str) -> Dict[str, Any]:
    url = f"{API_PREFIX}{tag_id}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()


def fmt_num(x: Optional[float]) -> str:
    if x is None:
        return ""
    return f"{float(x):.2f}".rstrip("0").rstrip(".")


def to_sheet_image_formula(image_url: str) -> str:
    if not image_url:
        return ""
    return f'=IMAGE("{image_url}")'


def extract_tag_id(user_input: str) -> str:
    s = (user_input or "").strip().rstrip("/")
    m = re.search(r"(\d+)\s*$", s)
    return m.group(1) if m else ""


def build_row(data: Dict[str, Any]) -> OfferRow:
    image_url = safe_get(data, "media_list[0].url", "")
    image_formula = to_sheet_image_formula(str(image_url))

    title = safe_get(data, "articles[0].title", "")
    desc = safe_get(data, "articles[0].description", "")
    article_id = safe_get(data, "articles[0].article_id", "")

    link_produktu = f"https://www.ikea.com/pl/pl/search/?q={article_id}" if article_id else ""

    catalog_price = safe_get(data, "articles[0].price", None)
    promo_price = safe_get(data, "price", None)
    discount_pct = calc_discount_percent(catalog_price, promo_price)

    reason_discount = safe_get(data, "reasonDiscount", "")
    state = safe_get(data, "state", "")

    unit_id = safe_get(data, "unitId", "")
    store_slug, store_name = store_from_unit_id(unit_id)

    tag_id = safe_get(data, "tagId", "")
    link_okazji = ""
    if store_slug and tag_id:
        link_okazji = f"https://www.ikea.com/pl/pl/second-hand/buy-from-ikea/#/{store_slug}/{tag_id}"

    return OfferRow(
        zdjecie=image_formula,
        nazwa=str(title),
        opis=str(desc),
        kod_artykulu=str(article_id),
        link_produktu=str(link_produktu),
        cena_katalogowa=float(catalog_price) if catalog_price not in (None, "") else None,
        cena_promocyjna=float(promo_price) if promo_price not in (None, "") else None,
        procent_obnizki=discount_pct,
        powod_obnizki_pl=str(reason_discount),
        status=str(state),
        link_okazji=str(link_okazji),
        sklep=str(store_name),
    )


def row_to_csv_line(row: OfferRow) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow([
        row.zdjecie,
        row.nazwa,
        row.opis,
        row.kod_artykulu,
        row.link_produktu,
        fmt_num(row.cena_katalogowa),
        fmt_num(row.cena_promocyjna),
        fmt_num(row.procent_obnizki),
        row.powod_obnizki_pl,
        row.status,
        row.link_okazji,
        row.sklep,
    ])
    return buf.getvalue().strip("\n")


# ===== UI =====
st.set_page_config(page_title="IKEA → CSV", layout="wide")

with st.sidebar:
    st.write("")

st.title("IKEA → CSV")

# Stan na wynik, żeby przycisk kopiowania działał po rerunie
if "csv_line" not in st.session_state:
    st.session_state.csv_line = ""

user_input = st.text_input("")

col_a, col_b = st.columns([1, 1], vertical_alignment="center")

with col_a:
    if st.button("Zrób CSV", type="primary"):
        try:
            tag_id = extract_tag_id(user_input)
            if not tag_id:
                raise ValueError("bad_input")

            data = fetch_offer(tag_id)
            row = build_row(data)
            st.session_state.csv_line = row_to_csv_line(row)
        except Exception:
            st.session_state.csv_line = ""
            st.toast("Błąd", icon="⚠️")

with col_b:
    if st.button("Kopiuj", disabled=(st.session_state.csv_line == "")):
        try:
            pyperclip.copy(st.session_state.csv_line)
            st.toast("Skopiowano!", icon="✅")
        except Exception:
            st.toast("Nie udało się skopiować", icon="❌")

st.text_area("", value=st.session_state.csv_line, height=90)

"""Presentation metadata for countries and outlets.

The designs need an identity colour, a native name, a political axis and a
five-position scale for every country, plus a native name and a 1-5 position
for every outlet. Postgres stores none of that yet: `countries` holds only a
name, and `sources.political_leaning` is a coarse left/center/right string.

This module is the single place that supplies the missing values, so when the
backend starts returning them only the two lookups below have to change.
"""

from typing import Optional


COUNTRIES = {
    "ir": {
        "key": "ir",
        "name": "Iran",
        "native_name": "ایران",
        "lang": "fa",
        "dir": "rtl",
        "colour": "#1E7353",
        "chart_colour": "#11825A",
        "axis_left_label": "Reformist",
        "axis_right_label": "Hardline",
        "position_labels": (
            "Reformist",
            "Reform-leaning",
            "Centrist",
            "Conservative",
            "Hardline",
        ),
        "status": "live",
        "city": "Tehran",
        "timezone": "Asia/Tehran",
        "capital": (51.39, 35.69),
        "atlas_id": "364",
    },
    "il": {
        "key": "il",
        "name": "Israel",
        "native_name": "ישראל",
        "lang": "he",
        "dir": "rtl",
        "colour": "#2B5BA6",
        "chart_colour": "#2B5BA6",
        "axis_left_label": "Left",
        "axis_right_label": "Right",
        "position_labels": (
            "Left",
            "Centre-left",
            "Centre",
            "Centre-right",
            "Right",
        ),
        "status": "live",
        "city": "Jerusalem",
        "timezone": "Asia/Jerusalem",
        "capital": (35.21, 31.77),
        "atlas_id": "376",
    },
    "ru": {
        "key": "ru",
        "name": "Russia",
        "native_name": "Россия",
        "lang": "ru",
        "dir": "ltr",
        "colour": "#56616B",
        "chart_colour": "#56616B",
        "axis_left_label": "Independent",
        "axis_right_label": "Pro-Kremlin",
        "position_labels": (
            "Independent, in exile",
            "Leans independent",
            "Establishment",
            "Leans pro-Kremlin",
            "Pro-Kremlin",
        ),
        "status": "next",
        "city": "Moscow",
        "timezone": "Europe/Moscow",
        "capital": (37.62, 55.75),
        "atlas_id": "643",
    },
    "ua": {
        "key": "ua",
        "name": "Ukraine",
        "native_name": "Україна",
        "lang": "uk",
        "dir": "ltr",
        "colour": "#B07D00",
        "chart_colour": "#B07D00",
        "axis_left_label": "Government-critical",
        "axis_right_label": "Pro-government",
        "position_labels": (
            "Government-critical",
            "Leans critical",
            "Independent",
            "Leans pro-government",
            "Pro-government",
        ),
        "status": "next",
        "city": "Kyiv",
        "timezone": "Europe/Kyiv",
        "capital": (30.52, 50.45),
        "atlas_id": "804",
    },
}

COUNTRY_KEYS_BY_NAME = {
    country["name"]: key for key, country in COUNTRIES.items()
}

LIVE_COUNTRY_KEYS = tuple(
    key for key, country in COUNTRIES.items() if country["status"] == "live"
)

# Outlet name -> (native name, position on its country's own 1-5 axis).
OUTLETS = {
    "Shargh": ("شرق", 1),
    "Etemad": ("اعتماد", 1),
    "Hamshahri": ("همشهری", 3),
    "Donya-e-Eqtesad": ("دنیای اقتصاد", 3),
    "Javan": ("جوان", 5),
    "Kayhan": ("کیهان", 5),
    "Tasnim": ("تسنیم", 5),
    "Fars": ("فارس", 5),
    "Haaretz": ("הארץ", 1),
    "Yedioth Ahronoth": ("ידיעות אחרונות", 3),
    "Globes": ("גלובס", 3),
    "Maariv": ("מעריב", 4),
    "Israel Hayom": ("ישראל היום", 5),
    "Makor Rishon": ("מקור ראשון", 5),
}

# Fallback for an outlet the registry does not know yet. Centre is tested
# first so that "centre-left" does not read as "left".
LEANING_POSITIONS = (
    ("center", 3),
    ("centre", 3),
    ("left", 1),
    ("right", 5),
)


def get_country(key_or_name: str) -> Optional[dict]:
    """Return a country's presentation metadata by key or by English name."""

    if key_or_name in COUNTRIES:
        return COUNTRIES[key_or_name]
    key = COUNTRY_KEYS_BY_NAME.get(key_or_name)
    return COUNTRIES.get(key) if key else None


def country_key(name: str) -> Optional[str]:
    """Return the two-letter key for a country's English name."""

    return COUNTRY_KEYS_BY_NAME.get(name)


def outlet_native_name(name: str) -> str:
    """Return an outlet's name in its own script, or its English name."""

    entry = OUTLETS.get(name)
    return entry[0] if entry else name


def outlet_position(name: str, political_leaning: str = "") -> int:
    """Return an outlet's position on its country's 1-5 axis.

    Falls back to the coarse `sources.political_leaning` string, which only
    distinguishes the two ends and the middle, and then to the centre.
    """

    entry = OUTLETS.get(name)
    if entry:
        return entry[1]

    label = (political_leaning or "").lower()
    for needle, position in LEANING_POSITIONS:
        if needle in label:
            return position
    return 3


def position_label(country_key_or_name: str, position: int) -> str:
    """Return the label for a position on that country's own axis."""

    country = get_country(country_key_or_name)
    if not country:
        return ""
    index = min(5, max(1, position)) - 1
    return country["position_labels"][index]

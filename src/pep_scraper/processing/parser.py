"""Regex-based extraction of PEP metadata from raw HTML."""

import html
import re
from collections.abc import Iterable
from typing import TypedDict

# <title>PEP 8 – Style Guide for Python Code | peps.python.org</title>
TITLE_RE = re.compile(r"<title>\s*PEP\s+(?P<number>\d+)\s*[–-]\s*(?P<title>.*?)\s*\|\s*peps\.python\.org\s*</title>", re.S)

# Each header field is a <dt>Name<span class="colon">:</span></dt> followed by its <dd>value</dd>.
FIELD_RE = re.compile(
    r"<dt[^>]*>\s*(?P<name>[\w-]+)\s*<span[^>]*>:</span>\s*</dt>\s*<dd[^>]*>(?P<value>.*?)</dd>",
    re.S,
)

TAG_RE = re.compile(r"<[^>]+>")
EMAIL_RE = re.compile(r"\s*<[^>]*>")       # "<guido at python.org>" once unescaped
WHITESPACE_RE = re.compile(r"\s+")


class PepRecord(TypedDict):
    number: int
    title: str
    authors: list[str]
    status: str | None
    type: str | None
    created: str | None
    python_version: str | None
    url: str


def clean_value(raw: str) -> str:
    """Strip markup, decode entities and collapse whitespace."""
    text = html.unescape(TAG_RE.sub("", raw))
    return WHITESPACE_RE.sub(" ", text).strip()


def parse_authors(raw: str) -> list[str]:
    """Turn 'Guido van Rossum <guido at python.org>, Barry Warsaw <...>' into names."""
    names = map(str.strip, EMAIL_RE.sub("", clean_value(raw)).split(","))
    return list(filter(None, names))


def extract_fields(page: str) -> dict[str, str]:
    """Return the raw (still marked-up) header fields keyed by field name."""
    return {m["name"]: m["value"] for m in FIELD_RE.finditer(page)}


def parse_pep(page: str, url: str) -> PepRecord | None:
    """Extract a ``PepRecord`` from a PEP page, or ``None`` if it isn't one."""
    title_match = TITLE_RE.search(page)
    if title_match is None:
        return None

    fields = extract_fields(page)

    def field(name: str) -> str | None:
        return clean_value(fields[name]) if name in fields else None

    return PepRecord(
        number=int(title_match["number"]),
        title=html.unescape(title_match["title"]),
        authors=parse_authors(fields.get("Author", "")),
        status=field("Status"),
        type=field("Type"),
        created=field("Created"),
        python_version=field("Python-Version"),
        url=url,
    )


def sort_records(records: Iterable[PepRecord]) -> list[PepRecord]:
    """Order records by PEP number for stable, readable output."""
    return sorted(records, key=lambda record: record["number"])

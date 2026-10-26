"""Read SCI RSS exports and convert their items to CSV."""

import io
import re
from pathlib import Path

import pandas as pd


def escape_bare_ampersands(xml: str) -> str:
    """Escape bare ampersands, preserving entities and protected XML sections."""
    return re.sub(
        r"<!\[CDATA\[.*?\]\]>|<!--.*?-->|<\?.*?\?>|"
        r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9A-Fa-f]+;)",
        lambda match: "&amp;" if match.group() == "&" else match.group(),
        xml,
        flags=re.DOTALL,
    )


def read_rss_items(xml_path: str | Path) -> pd.DataFrame:
    """Read UTF-8 RSS items; file and XML parsing errors propagate to the caller."""
    xml = Path(xml_path).read_text(encoding="utf-8")
    xml = escape_bare_ampersands(xml)
    return pd.read_xml(io.StringIO(xml), xpath="./channel/item", parser="etree")


def rss_to_csv_buffer(xml_path: str | Path) -> io.BytesIO:
    """Return UTF-8 CSV containing only dataset columns, positioned for reading."""
    csv_file = io.BytesIO()
    read_rss_items(xml_path).to_csv(csv_file, index=False)
    csv_file.seek(0)
    return csv_file

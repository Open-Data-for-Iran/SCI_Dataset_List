import csv
import io
import tempfile
import unittest
from pathlib import Path
from xml.etree.ElementTree import ParseError

from sci_dataset_list.parser import (
    escape_bare_ampersands,
    read_rss_items,
    rss_to_csv_buffer,
)


class ParserTests(unittest.TestCase):
    def test_repairs_ampersands_without_changing_entities_or_xml_sections(self):
        xml = (
            "A & B &unknown; &amp; &lt; &gt; &quot; &apos; &#38; &#x26;\n"
            "<![CDATA[A &\nB]]><!-- A &\nB --><?test A &\nB?>"
        )
        expected = xml.replace("A & B &unknown;", "A &amp; B &amp;unknown;")
        self.assertEqual(escape_bare_ampersands(xml), expected)
        self.assertEqual(escape_bare_ampersands(expected), expected)

    def test_reads_rss_and_returns_readable_utf8_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rss.xml"
            path.write_text(
                "<rss><channel><item><title>آمار & data</title>"
                "<description><![CDATA[A & B]]></description>"
                "</item></channel></rss>",
                encoding="utf-8",
            )
            self.assertEqual(
                read_rss_items(str(path)).to_dict("records"),
                [{"title": "آمار & data", "description": "A & B"}],
            )
            result = rss_to_csv_buffer(path)
            self.assertEqual(
                list(csv.reader(io.StringIO(result.read().decode("utf-8")))),
                [["title", "description"], ["آمار & data", "A & B"]],
            )

    def test_malformed_xml_still_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rss.xml"
            path.write_text("<rss><channel>", encoding="utf-8")
            with self.assertRaises(ParseError):
                read_rss_items(path)


if __name__ == "__main__":
    unittest.main()

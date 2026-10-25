from pep_scraper.processing.parser import clean_value, extract_fields, parse_authors, parse_pep, sort_records


def test_parse_pep_extracts_all_fields(pep_html):
    record = parse_pep(pep_html, "https://peps.python.org/pep-0008/")

    assert record == {
        "number": 8,
        "title": "Style Guide for Python Code",
        "authors": ["Guido van Rossum", "Łukasz Langa"],
        "status": "Final",
        "type": "Standards Track",
        "created": "01-Jan-2020",
        "python_version": "3.11",
        "url": "https://peps.python.org/pep-0008/",
    }


def test_parse_pep_handles_missing_optional_fields(make_pep_html):
    record = parse_pep(make_pep_html(20, python_version=None), "u")

    assert record["python_version"] is None
    assert record["status"] == "Final"


def test_parse_pep_rejects_non_pep_pages():
    assert parse_pep("<html><title>Python.org</title></html>", "u") is None


def test_parse_pep_decodes_entities_in_title():
    page = "<title>PEP 343 – The &#8220;with&#8221; Statement | peps.python.org</title>"

    assert parse_pep(page, "u")["title"] == "The “with” Statement"


def test_extract_fields_maps_names_to_raw_values(pep_html):
    fields = extract_fields(pep_html)

    assert list(fields) == ["Author", "Status", "Type", "Created", "Python-Version"]
    assert "<abbr" in fields["Status"]


def test_clean_value_strips_tags_and_whitespace():
    assert clean_value('<abbr title="x">Standards\n   Track</abbr>') == "Standards Track"


def test_parse_authors_drops_emails_and_blanks():
    raw = "Chris Angelico &lt;rosuav at gmail.com&gt;, Tim Peters &lt;tim at gmail.com&gt;,\n, Guido van Rossum"

    assert parse_authors(raw) == ["Chris Angelico", "Tim Peters", "Guido van Rossum"]


def test_sort_records_orders_by_number(make_pep_html):
    records = [parse_pep(make_pep_html(n), "u") for n in (572, 8, 20)]

    assert [r["number"] for r in sort_records(records)] == [8, 20, 572]

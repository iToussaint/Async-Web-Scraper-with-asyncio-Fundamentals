import json

from pep_scraper.storage import save_json


async def test_save_json_creates_directories_and_keeps_unicode(tmp_path):
    data = {"authors": ["Łukasz Langa"], "count": 1}

    path = await save_json(data, "peps.json", tmp_path / "nested" / "output")

    assert path == tmp_path / "nested" / "output" / "peps.json"
    text = path.read_text(encoding="utf-8")
    assert "Łukasz" in text  # written as-is, not \u escaped
    assert json.loads(text) == data


async def test_save_json_overwrites_existing_file(tmp_path):
    await save_json({"run": 1}, "report.json", tmp_path)
    path = await save_json({"run": 2}, "report.json", tmp_path)

    assert json.loads(path.read_text(encoding="utf-8")) == {"run": 2}

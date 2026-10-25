import json

from pep_scraper import scraper


async def test_scrape_builds_report_from_local_server(pep_server):
    base_url = pep_server.base_url

    report = await scraper.scrape(numbers=[572, 8, 20], base_url=base_url)

    assert report["total_urls"] == 3
    assert report["succeeded"] == 3
    assert report["failed"] == []
    assert [pep["number"] for pep in report["peps"]] == [8, 20, 572]
    assert report["source"] == base_url


async def test_scrape_lists_failures(pep_server, monkeypatch):
    base_url = pep_server.base_url
    bad_urls = iter([f"{base_url}/pep-0008/", f"{base_url}/missing", f"{base_url}/not-a-pep"])
    monkeypatch.setattr(scraper, "generate_pep_urls", lambda numbers, base: bad_urls)

    report = await scraper.scrape(numbers=[0, 0, 0], base_url=base_url)

    assert report["succeeded"] == 1
    assert sorted(report["failed"], key=lambda f: f["url"]) == [
        {"url": f"{base_url}/missing", "error": "HTTP 404"},
        {"url": f"{base_url}/not-a-pep", "error": "page is not a PEP document"},
    ]


async def test_run_writes_report(tmp_path, monkeypatch):
    async def fake_scrape():
        return {"succeeded": 0, "total_urls": 0, "elapsed_seconds": 0.0, "peps": []}

    monkeypatch.setattr(scraper, "scrape", fake_scrape)

    path = await scraper.run(output_dir=tmp_path)

    assert path == tmp_path / "peps.json"
    assert json.loads(path.read_text(encoding="utf-8"))["peps"] == []

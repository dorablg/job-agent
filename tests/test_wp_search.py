from agent import sources


class FakeResp:
    def __init__(self, data):
        self._data, self.ok = data, True

    def json(self):
        return self._data


def test_wp_search_parallel_sites_keep_order_and_dedupe(monkeypatch):
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)
    posts = {
        "https://a.example": [{"link": "https://a.example/p1", "title": {"rendered": "AI Fellowship 2027"},
                               "content": {"rendered": "<p>Fully funded AI fellowship.</p>"}, "date": "2026-11-01T00:00:00"},
                              {"link": "https://a.example/tips", "title": {"rendered": "How to win scholarships"},
                               "content": {"rendered": "advice"}, "date": "2026-11-01T00:00:00"}],
        "https://b.example": [{"link": "https://a.example/p1", "title": {"rendered": "dupe"}, "content": {"rendered": ""}},
                              {"link": "https://b.example/p2", "title": {"rendered": "Data Science Summer School"},
                               "content": {"rendered": "<p>Free summer school.</p>"}, "date": "2026-11-02T00:00:00"}],
    }

    def fake_get(url, **kw):
        site = url.split("/wp-json")[0]
        return FakeResp(posts[site] if kw["params"]["search"] == "ai" else [])

    monkeypatch.setattr(sources, "http_get", fake_get)
    out = sources.wp_search(None, {"sites": ["https://a.example", "https://b.example"], "queries": ["ai", "data"]})
    assert [j.url for j in out] == ["https://a.example/p1", "https://b.example/p2"]
    assert out[0].source == "a.example" and out[0].description.startswith("Fully funded")

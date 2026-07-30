from urllib.parse import parse_qs

import httpx

import music_sources
from music_sources import NeteaseResolver, parse_lrc


def test_lrc_parser_sorts_rows_and_ignores_metadata():
    rows = parse_lrc(
        "[ar:Alive]\n[00:12.50]第二句\n[00:01.250]第一句\n[00:01.250]\n"
    )
    assert [row["text"] for row in rows] == ["第一句", "第二句"]
    assert rows[0]["time"] == 1.25


def test_netease_resolver_returns_stable_visitor_stream_without_credentials(
    monkeypatch,
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert "Cookie" not in request.headers
        assert "Authorization" not in request.headers
        kind = parse_qs(request.url.query.decode())["type"][0]
        if kind == "song":
            return httpx.Response(
                200,
                json=[
                    {
                        "name": "公开歌曲",
                        "artist": "Alive",
                        "pic": "https://api.example.test/pic",
                    }
                ],
            )
        if kind == "lrc":
            return httpx.Response(200, text="[00:01.00]公开歌词")
        raise AssertionError(f"unexpected resolver request: {request.url}")

    real_client = httpx.Client

    def client_factory(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(**kwargs)

    monkeypatch.setattr(music_sources.httpx, "Client", client_factory)
    resolver = NeteaseResolver()
    result = resolver.resolve(
        "33894312",
        ["https://api.example.test/meting/"],
        2,
    )
    assert result.available is True
    assert result.title == "公开歌曲"
    assert result.audio_url == (
        "https://api.example.test/meting/"
        "?server=netease&type=url&id=33894312"
    )
    assert result.lyrics[0]["text"] == "公开歌词"
    assert len(requests) == 2

    cached = resolver.resolve(
        "33894312",
        ["https://api.example.test/meting/"],
        2,
    )
    assert cached == result
    assert len(requests) == 2

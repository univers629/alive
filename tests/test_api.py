import asyncio
import io
import hashlib
import json
import os
from pathlib import Path

os.environ["alive_main_database"] = "sqlite:///:memory:"
os.environ["alive_main_secret"] = "test-secret-1234"
os.environ["alive_main_colorful_log"] = "false"
os.environ["alive_page_more_text"] = "累计访问 {visit_total} 次"

from fastapi.testclient import TestClient
from PIL import Image

import main
from music_sources import NeteaseResolution


def test_status_stream_tracks_connected_viewers():
    class ConnectedRequest:
        @staticmethod
        async def is_disconnected():
            return False

    async def read_first_update():
        initial = main._active_viewers
        stream = main._event_stream(ConnectedRequest(), 0)
        event = await anext(stream)
        payload = json.loads(event.split("data: ", 1)[1])
        assert payload["online_viewers"] == initial + 1
        await stream.aclose()
        assert main._active_viewers == initial

    asyncio.run(read_first_update())


def test_bilingual_docs_and_chinese_openapi():
    assert main.MIN_SECRET_LENGTH == 6
    main._validate_main_secret("123456")
    try:
        main._validate_main_secret("12345")
    except RuntimeError:
        pass
    else:
        raise AssertionError("five-character secrets must be rejected")

    with TestClient(main.app) as client:
        docs = client.get("/docs")
        assert docs.status_code == 200
        assert "Alive API 文档" in docs.text
        assert 'id="language-toggle"' in docs.text
        assert client.get("/swagger").status_code == 200

        schema = client.get("/openapi.json").json()
        assert schema["paths"]["/api/status/set"]["post"]["summary"] == "设置手动状态"
        assert client.get("/api/meta").json()["status"]["device_timeout"] == 150


def test_post_only_mutations_and_public_reads():
    with TestClient(main.app) as client:
        assert client.get("/api/meta").json()["framework"] == "FastAPI"
        assert client.get("/api/status/query").status_code == 200
        assert client.get("/api/status/list").status_code == 200

        assert client.get("/api/device/set").status_code == 405
        assert client.get("/api/status/set").status_code == 405
        assert client.get("/api/device/remove").status_code == 405
        assert client.get("/api/device/clear").status_code == 405
        assert client.get("/api/device/private").status_code == 405
        assert client.get("/api/health/set").status_code == 405
        assert client.get("/api/health/clear").status_code == 405
        assert client.get("/api/music/set").status_code == 405
        assert client.get("/api/music/clear").status_code == 405
        assert client.get("/api/music/cover").status_code == 405
        assert client.get("/api/music/player-icon").status_code == 405
        assert client.get("/api/device/app-icon").status_code == 405
        assert client.get("/api/music/track/check").status_code == 405
        assert client.get("/api/music/track/upload").status_code == 405
        assert client.get("/api/admin/music/account/save").status_code == 404
        assert client.get("/api/admin/music/account/test").status_code == 404
        assert client.get("/api/admin/music/account/remove").status_code == 404
        assert client.get("/api/admin/secret").status_code == 405

        unauthorized = client.post(
            "/api/device/set",
            json={"id": "blocked", "show_name": "Blocked", "using": True},
        )
        assert unauthorized.status_code == 401

        headers = {"Authorization": "Bearer test-secret-1234"}
        icon = b"\x89PNG\r\n\x1a\n" + b"alive-app-icon"
        uploaded_icon = client.post(
            "/api/device/app-icon",
            headers={**headers, "Content-Type": "image/png"},
            content=icon,
        )
        assert uploaded_icon.status_code == 200
        assert uploaded_icon.json()["url"].startswith("/app-icons/")
        Path(
            main.u.get_path(
                "data/public/" + uploaded_icon.json()["url"].lstrip("/")
            )
        ).unlink(missing_ok=True)
        player_icon = client.post(
            "/api/music/player-icon",
            headers={**headers, "Content-Type": "image/png"},
            content=icon,
        )
        assert player_icon.status_code == 200
        assert player_icon.json()["url"].startswith("/music-player-icons/")
        Path(
            main.u.get_path(
                "data/public/" + player_icon.json()["url"].lstrip("/")
            )
        ).unlink(missing_ok=True)
        created = client.post(
            "/api/device/set",
            headers=headers,
            json={
                "id": "desktop",
                "show_name": "Desktop",
                "using": True,
                "status": "Editor",
                "fields": {
                    "device_type": "desktop",
                    "platform": "Windows 11",
                    "cpu_cores": 16,
                    "memory_gb": 32,
                },
            },
        )
        assert created.status_code == 200
        second = client.post(
            "/api/device/set",
            headers=headers,
            json={
                "id": "shared-secret-phone",
                "show_name": "Shared Secret Phone",
                "using": True,
                "status": "Phone",
            },
        )
        assert second.status_code == 200

        query = client.get("/api/status/query").json()
        assert query["device"]["desktop"]["status"] == "Editor"
        assert query["device"]["desktop"]["fields"]["platform"] == "Windows 11"
        assert query["device"]["desktop"]["fields"]["cpu_cores"] == 16
        assert query["device"]["desktop"]["fields"]["memory_gb"] == 32
        assert query["device"]["shared-secret-phone"]["status"] == "Phone"

        # Legacy clients may omit the fields object entirely, or only send the
        # original battery/network payload. Activity tracking is opt-in.
        legacy = client.post(
            "/api/device/set",
            headers=headers,
            json={"id": "legacy-client", "show_name": "Legacy Client", "using": True, "status": "Browser"},
        )
        assert legacy.status_code == 200
        legacy_fields = client.post(
            "/api/device/set",
            headers=headers,
            json={
                "id": "legacy-fields-client",
                "show_name": "Legacy Fields Client",
                "using": True,
                "status": "Phone",
                "fields": {"battery": 80, "network_type": "Wi-Fi"},
            },
        )
        assert legacy_fields.status_code == 200
        assert client.get("/api/details/query").json()["activity"]["total_records"] == 0

        private = client.post(
            "/api/device/private",
            headers=headers,
            json={"private": True},
        )
        assert private.status_code == 200
        assert client.get("/api/status/query").json()["private_mode"] is True

        client.post(
            "/api/device/private",
            headers=headers,
            json={"private": False},
        )
        removed = client.post(
            "/api/device/remove",
            headers=headers,
            json={"id": "desktop"},
        )
        assert removed.status_code == 200
        assert client.post(
            "/api/device/remove",
            headers=headers,
            json={"id": "shared-secret-phone"},
        ).status_code == 200


def test_health_state_persists_and_is_in_status_stream_payload():
    with TestClient(main.app) as client:
        headers = {"Authorization": "Bearer test-secret-1234"}
        updated = client.post(
            "/api/health/set",
            headers=headers,
            json={
                "heart_rate": 76,
                "resting_heart_rate": 61,
                "heart_rate_min": 55,
                "heart_rate_max": 128,
                "steps": 6248,
                "step_goal": 8000,
                "source": "Health Connect",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["health"]["heart_rate"] == 76
        public = client.get("/api/status/query").json()["health"]
        assert public["active"] is True
        assert public["steps"] == 6248
        assert public["source"] == "Health Connect"
        assert client.post("/api/health/clear", headers=headers, json={}).status_code == 200
        assert client.get("/api/health/query").json()["health"]["active"] is False


def test_music_state_and_timestamped_lyrics_use_authenticated_post():
    with TestClient(main.app) as client:
        unauthorized = client.post(
            "/api/music/set",
            json={"title": "Blocked"},
        )
        assert unauthorized.status_code == 401

        headers = {"Authorization": "Bearer test-secret-1234"}
        updated = client.post(
            "/api/music/set",
            headers=headers,
            json={
                "device_id": "desktop",
                "title": "夜航",
                "artist": "Alive",
                "album": "Local Test",
                "player_name": "Windows 媒体播放器",
                "player_icon": "media-player",
                "player_icon_url": "/music-player-icons/abc.png",
                "duration": 180,
                "position": 12.5,
                "playing": True,
                "lyrics": [
                    {"time": 9, "text": "第二句"},
                    {"time": 0, "text": "第一句", "translation": "First line"},
                ],
            },
        )
        assert updated.status_code == 200
        assert updated.json()["music"]["lyrics"][0]["text"] == "第一句"

        public = client.get("/api/music/query").json()["music"]
        assert public["active"] is True
        assert public["title"] == "夜航"
        assert public["playing"] is True
        assert public["player_name"] == "Windows 媒体播放器"
        assert public["player_icon_url"] == "/music-player-icons/abc.png"
        assert client.get("/api/status/query").json()["music"]["artist"] == "Alive"

        cleared = client.post("/api/music/clear", headers=headers, json={})
        assert cleared.status_code == 200
        assert client.get("/api/music/query").json()["music"]["active"] is False


def test_netease_music_uses_visitor_side_public_stream(monkeypatch):
    monkeypatch.setattr(
        main.netease_resolver,
        "resolve",
        lambda song_id, api_values, timeout: NeteaseResolution(
            available=True,
            song_id=song_id,
            title="接口歌名",
            artist="接口歌手",
            cover_url="https://api.example.test/cover",
            audio_url="https://api.example.test/audio",
            lyrics=({"time": 1.5, "text": "同步歌词", "translation": ""},),
        ),
    )
    headers = {"Authorization": "Bearer test-secret-1234"}
    with TestClient(main.app) as client:
        response = client.post(
            "/api/music/set",
            headers=headers,
            json={
                "source_mode": "netease-api",
                "source_id": "33894312",
                "title": "媒体会话歌名",
                "duration": 180,
                "position": 12,
                "playing": True,
            },
        )
        assert response.status_code == 200
        music = response.json()["music"]
        assert music["source_mode"] == "netease-api"
        assert music["source_id"] == "33894312"
        assert music["title"] == "媒体会话歌名"
        assert music["artist"] == "接口歌手"
        assert music["audio_url"] == "https://api.example.test/audio"
        assert music["lyrics"][0]["text"] == "同步歌词"
        assert "Alive 不保存网易云音频" in music["source_status"]
        client.post("/api/music/clear", headers=headers, json={})


def test_music_account_credential_routes_are_removed():
    headers = {"Authorization": "Bearer test-secret-1234"}
    with TestClient(main.app) as client:
        snapshot = client.get("/api/admin/snapshot", headers=headers).json()
        assert "music_account" not in snapshot
        openapi_paths = client.get("/openapi.json").json()["paths"]
        assert "/api/admin/music/account/save" not in openapi_paths
        assert "/api/admin/music/account/test" not in openapi_paths
        assert "/api/admin/music/account/remove" not in openapi_paths


def test_music_track_is_deduplicated_uploaded_and_publicly_streamed(tmp_path):
    original_library = main.c.main.music_library
    main.c.main.music_library = str(tmp_path / "music-library")
    audio = b"ID3" + b"\x04\x00\x00\x00\x00\x00\x00" + b"alive-audio-test"
    digest = hashlib.sha256(audio).hexdigest()
    headers = {"Authorization": "Bearer test-secret-1234"}
    try:
        with TestClient(main.app) as client:
            check = client.post(
                "/api/music/track/check",
                headers=headers,
                json={"sha256": digest, "suffix": ".mp3", "size": len(audio)},
            )
            assert check.status_code == 200
            assert check.json()["exists"] is False

            upload = client.post(
                "/api/music/track/upload",
                headers={
                    **headers,
                    "Content-Type": "audio/mpeg",
                    "Content-Length": str(len(audio)),
                    "X-Alive-Audio-Sha256": digest,
                    "X-Alive-Audio-Suffix": ".mp3",
                },
                content=audio,
            )
            assert upload.status_code == 200
            library_path = upload.json()["library_path"]
            assert library_path == f"{digest[:2]}/{digest}.mp3"

            duplicate = client.post(
                "/api/music/track/check",
                headers=headers,
                json={"sha256": digest, "suffix": ".mp3", "size": len(audio)},
            )
            assert duplicate.json()["exists"] is True

            state = client.post(
                "/api/music/set",
                headers=headers,
                json={
                    "title": "已上传歌曲",
                    "artist": "Alive",
                    "library_path": library_path,
                    "duration": 60,
                    "position": 2,
                    "playing": True,
                },
            )
            audio_url = state.json()["music"]["audio_url"]
            streamed = client.get(audio_url)
            assert streamed.status_code == 200
            assert streamed.content == audio
            assert client.post("/api/music/clear", headers=headers, json={}).status_code == 200
    finally:
        main.c.main.music_library = original_library


def test_home_includes_new_music_island_without_legacy_playlist_api():
    with TestClient(main.app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert 'id="music-island"' in home.text
        assert "music-island.js" in home.text
        assert "page-shell.css" in home.text
        assert "color-mode.css" in home.text
        assert "color-mode.js" in home.text
        assert "glass-select.css" in home.text
        assert "glass-select.js" in home.text
        assert 'id="color-mode-toggle"' in home.text
        assert 'class="color-mode-toggle__track"' in home.text
        assert "color-mode-toggle__sun" not in home.text
        assert "color-mode-toggle__moon" not in home.text
        assert 'class="site-topbar"' in home.text
        assert 'id="site-menu-toggle"' in home.text
        assert 'href="/details"' in home.text
        assert 'href="/panel"' in home.text
        assert home.text.count('href="/panel"') == 1
        assert home.text.count('href="/docs"') == 1
        assert 'class="site-topbar__brand"' not in home.text
        assert 'class="site-topbar__actions"' in home.text
        assert 'id="visit-metric"' in home.text
        assert 'id="online-viewer-count"' in home.text
        assert "已被视奸" in home.text
        assert "正在视奸" in home.text
        assert 'class="site-footer"' in home.text
        assert "你可以通过这个页面视奸" not in home.text
        assert 'id="more-info"' not in home.text
        assert 'class="site-drawer__number">03' not in home.text
        assert 'class="site-drawer__number">04' not in home.text
        assert 'id="comment-wall"' in home.text
        assert "comment-wall.js" in home.text
        assert "一起听" in home.text
        assert "机主播放进度 · 仅查看" in home.text
        assert 'class="music-island__speaker"' in home.text
        assert "music-island__chevron" not in home.text
        assert 'class="music-island__lyrics"' not in home.text
        assert 'class="music-island__progress" type="range"' not in home.text
        assert 'class="device-grid"' in home.text
        assert "device-cards.css" in home.text
        assert '<main class="container" id="main-content">' in home.text
        assert 'id="site-drawer" aria-hidden="true" aria-label="更多页面" inert' in home.text
        assert "?v=1.0.0?v=" not in home.text
        assert 'class="health-overview__grid"' in home.text
        assert "身体状态" in home.text

        device_script = client.get("/static/get.js").text
        assert "cpu_cores" in device_script
        assert "GB 内存" in device_script
        assert "心率" in home.text
        assert "今日步数" in home.text
        assert "随身手机" not in home.text
        assert "床头平板" not in home.text
        assert "等待真机上报" in home.text
        assert "6,248" not in home.text
        assert "请输入网易云歌单ID" not in home.text

        assert main.u.themes_available() == ["default"]
        legacy_theme_query = client.get("/", params={"theme": "dark"})
        assert legacy_theme_query.status_code == 200
        assert 'id="color-mode-toggle"' in legacy_theme_query.text
        assert "alive-theme=" not in legacy_theme_query.headers.get("set-cookie", "")
        assert client.get("/api/meta").json()["page"]["theme"] == "default"
        assert client.get("/api/status/query").json()["online_viewers"] >= 0

        topbar_css = client.get("/static/site-chrome.css").text
        assert "top: 0;" in topbar_css
        assert "width: 100%;" in topbar_css
        assert "border-radius: 0;" in topbar_css

        direct_asset = client.get("/static/main.css", follow_redirects=False)
        assert direct_asset.status_code == 200
        assert direct_asset.headers["cache-control"] == "no-cache"
        versioned_asset = client.get("/static/main.css?v=test", follow_redirects=False)
        assert versioned_asset.status_code == 200
        assert versioned_asset.headers["cache-control"] == "public, max-age=31536000, immutable"
        background_worker = client.get("/static/background-cache.js?v=test", follow_redirects=False)
        assert background_worker.status_code == 200
        assert background_worker.headers["service-worker-allowed"] == "/"
        assert "alive-image-cache-v1" in background_worker.text

        home = client.get("/")
        assert "background-cache.js" in home.text
        assert "serviceWorker.register" in home.text

        mode_css = client.get("/static/color-mode.css").text
        assert 'content: "☀";' in mode_css
        assert 'content: "☾";' in mode_css

        music_css = client.get("/static/music-island.css").text
        assert "right: calc(24px + env(safe-area-inset-right));" in music_css
        assert "bottom: calc(24px + env(safe-area-inset-bottom));" in music_css
        assert "left: 50%;" not in music_css
        music_js = client.get("/static/music-island.js").text
        assert "elements.join.disabled = !state?.audio_url && !joined;" in music_js
        assert "已开启一起听，等待下一首可用音源" in music_js
        assert "if (!state.audio_url) leaveTogether();" not in music_js
        assert "当前音源不可用，将在切歌后自动重试" in music_js

        chrome_css = client.get("/static/site-chrome.css").text
        assert ".site-topbar__admin {\n  height: 28px;" in chrome_css
        assert "background: transparent;" in chrome_css
        assert "pointer-events: none;" in chrome_css

        danmaku_css = client.get("/static/comment-wall.css").text
        assert ".comment-wall__stage {\n  position: fixed;" in danmaku_css
        assert "z-index: 1150;" in danmaku_css
        assert "comment-wall-flight-rtl" in danmaku_css
        assert "comment-wall-flight-ltr" in danmaku_css
        assert ".comment-wall__list::-webkit-scrollbar-track {" in danmaku_css
        assert "scrollbar-color:" in danmaku_css

        danmaku_js = client.get("/static/comment-wall.js").text
        assert "commentDisplayLimit = Number(root.dataset.displayLimit) || 8" in danmaku_js
        assert "replayInterval = Number(root.dataset.replayInterval) || 30" in danmaku_js
        assert "function replayDanmakuBatch()" in danmaku_js
        assert ".comment-wall__item--pinned" in danmaku_css
        assert "window.setInterval(replayDanmakuBatch, replayInterval * 1000)" in danmaku_js

        footer = client.get("/").text
        assert 'href="https://github.com/Alive-Project"' in footer
        assert "img/alive-project-icon.png" in footer
        assert 'loading="lazy" decoding="async"' in footer

        device_css = client.get("/static/device-cards.css").text
        assert ".health-overview__grid {" in device_css
        assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in device_css
        assert ".steps-card__ring {" in device_css
        assert ".tablet-device-icon {" in device_css
        assert "width: 25px;" in device_css
        assert "height: 17px;" in device_css

        select_css = client.get("/static/glass-select.css").text
        assert "border-radius: 999px;" in select_css
        assert "backdrop-filter: blur(30px) saturate(160%);" in select_css
        assert ".glass-select__menu {" in select_css

        select_js = client.get("/static/glass-select.js").text
        assert "new MutationObserver" in select_js
        assert "select.dispatchEvent(new Event('change'" in select_js
        assert "select.getBoundingClientRect()" not in select_js

        panel = client.get(
            "/panel",
            headers={"Authorization": "Bearer test-secret-1234"},
        )
        assert panel.status_code == 200
        assert "MUSIC_U" not in panel.text
        assert "网易云账号与解析接口" not in panel.text


def test_details_page_uses_real_metrics_and_sortable_device_snapshot():
    with TestClient(main.app) as client:
        headers = {"Authorization": "Bearer test-secret-1234"}
        created = client.post(
            "/api/device/set",
            headers=headers,
            json={
                "id": "details-device",
                "show_name": "Details Device",
                "using": True,
                "status": "Testing details",
                "fields": {
                    "platform": "Windows",
                    "activity_reporting": True,
                    "activity_device_type": "desktop",
                    "activity_app_id": "code",
                    "activity_app_name": "Visual Studio Code",
                    "activity_app_icon_url": "/app-icons/code.png",
                    "activity_title": "test_api.py - Alive",
                },
            },
        )
        assert created.status_code == 200

        page = client.get("/details")
        assert page.status_code == 200
        assert "glass-select.css" in page.text
        assert "glass-select.js" in page.text
        assert 'aria-current="page"' in page.text
        assert 'id="details-device-sort"' in page.text
        assert "应用使用记录" in page.text
        assert 'id="details-activity-list"' in page.text
        assert "details.js" in page.text

        mobile_created = client.post(
            "/api/device/set",
            headers=headers,
            json={
                "id": "details-phone",
                "show_name": "Details Phone",
                "using": True,
                "status": "Phone details",
                "fields": {
                    "activity_reporting": True,
                    "activity_device_type": "mobile",
                    "activity_app_id": "com.example.mobile",
                    "activity_app_name": "Mobile App",
                },
            },
        )
        assert mobile_created.status_code == 200

        details = client.get("/api/details/query")
        assert details.status_code == 200
        payload = details.json()
        assert payload["success"] is True
        assert payload["history_available"] is True
        assert payload["activity"]["total_records"] >= 1
        assert payload["activity"]["categories"]["desktop"]["recent"][0]["app_name"] == "Visual Studio Code"
        assert payload["activity"]["categories"]["desktop"]["recent"][0]["app_icon_url"] == "/app-icons/code.png"
        assert payload["activity"]["categories"]["desktop"]["recent"][0]["events"][0]["event_type"] == "app_open"
        assert payload["activity"]["categories"]["mobile"]["recent"][0]["app_name"] == "Mobile App"
        weekly = client.get("/api/details/query?period=weekly")
        assert weekly.status_code == 200
        weekly_activity = weekly.json()["activity"]
        assert weekly_activity["period"] == "weekly"
        assert len(weekly_activity["categories"]["desktop"]["time_series"]) == 7
        monthly = client.get("/api/details/query?period=monthly")
        assert monthly.status_code == 200
        assert len(monthly.json()["activity"]["categories"]["mobile"]["time_series"]) >= 28
        assert payload["visits"]["total"] >= payload["visits"]["daily"]
        assert payload["device_counts"]["total"] >= 1
        assert any(device["id"] == "details-device" for device in payload["devices"])
        assert "当前状态为" in payload["summary"]

        removed = client.post(
            "/api/device/remove",
            headers=headers,
            json={"id": "details-device"},
        )
        assert removed.status_code == 200


def test_public_comments_are_persistent_rate_limited_and_admin_removable():
    with TestClient(main.app) as client:
        visitor_headers = {"X-Forwarded-For": "203.0.113.77"}
        created = client.post(
            "/api/comments/create",
            headers=visitor_headers,
            json={
                "nickname": "",
                "content": "  来过，也听到了这首歌。  ",
                "color": "cyan",
                "website": "",
            },
        )
        assert created.status_code == 200
        comment = created.json()["comment"]
        assert comment["nickname"] == "匿名访客"
        assert comment["content"] == "来过，也听到了这首歌。"
        assert comment["color"] == "cyan"
        assert "visitor_hash" not in comment

        comments = client.get("/api/comments/query", params={"limit": 20})
        assert comments.status_code == 200
        assert comments.json()["danmaku_enabled"] is True
        assert len(comments.json()["comments"]) <= 8
        assert comments.json()["comments"][-1]["id"] == comment["id"]

        too_fast = client.post(
            "/api/comments/create",
            headers=visitor_headers,
            json={"content": "第二条太快了"},
        )
        assert too_fast.status_code == 429
        assert client.get("/api/comments/create").status_code == 405

        unauthorized = client.post(
            "/api/admin/comments/remove",
            json={"id": comment["id"]},
        )
        assert unauthorized.status_code == 401

        removed = client.post(
            "/api/admin/comments/remove",
            headers={"Authorization": "Bearer test-secret-1234"},
            json={"id": comment["id"]},
        )
        assert removed.status_code == 200
        remaining_ids = {
            item["id"]
            for item in client.get("/api/comments/query").json()["comments"]
        }
        assert comment["id"] not in remaining_ids


def test_admin_comment_flags_reorder_and_panel_controls():
    headers = {"Authorization": "Bearer test-secret-1234"}
    with TestClient(main.app) as client:
        created = client.post(
            "/api/comments/create",
            headers={"X-Forwarded-For": "198.51.100.31"},
            json={"content": "可管理评论"},
        )
        assert created.status_code == 200
        comment_id = created.json()["comment"]["id"]
        updated = client.post(
            "/api/admin/comments/update",
            headers=headers,
            json={"id": comment_id, "favorite": True, "pinned": True},
        )
        assert updated.status_code == 200
        assert updated.json()["comment"]["favorite"] is True
        assert updated.json()["comment"]["pinned"] is True
        public_comments = client.get("/api/comments/query").json()["comments"]
        assert public_comments[0]["id"] == comment_id
        assert public_comments[0]["pinned"] is True
        assert client.get("/api/admin/comments/update").status_code == 405
        assert client.post(
            "/api/admin/comments/update",
            headers=headers,
            json={"id": comment_id, "favorite": "yes", "pinned": True},
        ).status_code == 400

        client.post("/api/device/set", headers=headers, json={"id": "reorder-a", "show_name": "A"})
        client.post("/api/device/set", headers=headers, json={"id": "reorder-b", "show_name": "B"})
        client.post("/api/admin/device/profile", headers=headers, json={"id": "reorder-a", "sort_order": 10000})
        client.post("/api/admin/device/profile", headers=headers, json={"id": "reorder-b", "sort_order": 10001})
        before = list(client.get("/api/admin/snapshot", headers=headers).json()["devices"])
        moved = client.post(
            "/api/admin/device/reorder",
            headers=headers,
            json={"id": "reorder-b", "direction": "up"},
        )
        assert moved.status_code == 200
        after = list(moved.json()["devices"])
        assert moved.json()["device_order"] == after
        assert after.index("reorder-b") == before.index("reorder-a")
        assert after.index("reorder-a") == before.index("reorder-b")
        homepage_order = list(client.get("/api/status/query").json()["device"])
        assert homepage_order.index("reorder-b") < homepage_order.index("reorder-a")
        homepage_payload = client.get("/api/status/query").json()
        assert homepage_payload["device_order"] == list(homepage_payload["device"])

        client.post("/api/device/set", headers=headers, json={"id": "visible-top", "show_name": "Visible Top"})
        client.post("/api/device/set", headers=headers, json={"id": "hidden-middle", "show_name": "Hidden Middle"})
        client.post("/api/device/set", headers=headers, json={"id": "visible-bottom", "show_name": "Visible Bottom"})
        for device_id, sort_order, is_public in (
            ("visible-top", 20_000, True),
            ("hidden-middle", 20_001, False),
            ("visible-bottom", 20_002, True),
        ):
            client.post(
                "/api/admin/device/profile",
                headers=headers,
                json={"id": device_id, "display_name": device_id, "icon_key": "desktop", "sort_order": sort_order, "public": is_public},
            )
        moved_public = client.post(
            "/api/admin/device/reorder",
            headers=headers,
            json={"id": "visible-top", "direction": "down"},
        )
        assert moved_public.status_code == 200
        homepage_order = list(client.get("/api/status/query").json()["device"])
        assert homepage_order.index("visible-bottom") < homepage_order.index("visible-top")
        assert client.post(
            "/api/admin/device/reorder",
            headers=headers,
            json={"id": "reorder-b", "direction": "sideways"},
        ).status_code == 400

        panel = client.get("/panel", headers=headers)
        assert 'id="profile-avatar-file" class="visually-hidden-file"' in panel.text
        assert 'id="choose-profile-avatar-btn"' in panel.text
        assert 'id="social-links-editor"' in panel.text
        assert 'id="comments-list"' in panel.text
        assert "id=\"danmaku-enabled\"" in panel.text
        assert "sort_order" not in panel.text
        assert "bilibili" in client.get("/static/panel.js").text

        cleared = client.post("/api/admin/comments/clear", headers=headers)
        assert cleared.status_code == 200


def test_admin_can_choose_public_visit_period_and_edit_device_profile(tmp_path):
    with TestClient(main.app) as client:
        assert client.get("/api/admin/snapshot").status_code == 401
        assert client.get("/api/admin/settings").status_code == 405
        assert client.get("/api/admin/device/profile").status_code == 405

        client.post("/panel/auth", json={"secret": "test-secret-1234"})
        created = client.post(
            "/api/device/set",
            json={
                "id": "editable-device",
                "show_name": "Client Name",
                "using": True,
                "status": "Editor",
            },
        )
        assert created.status_code == 200

        settings = client.post(
            "/api/admin/settings",
            json={
                "visit_display_mode": "monthly",
                "danmaku_enabled": False,
                "health_section_enabled": False,
                "comment_display_limit": 12,
                "danmaku_replay_count": 3,
                "danmaku_replay_interval": 45,
                "page_name": "Codex",
                "page_title": "Codex Status",
                "social_links": [
                    {"platform": "github", "url": "https://github.com/univers629"},
                    {"platform": "email", "url": "codex@example.com"},
                ],
                "online_status_desc": "现在可以联系我。",
                "offline_status_desc": "现在暂时无法联系。",
                "music_library": str(tmp_path / "music"),
            },
        )
        assert settings.status_code == 200
        assert settings.json()["visit_metric"]["mode"] == "monthly"
        assert settings.json()["settings"]["danmaku_enabled"] is False
        assert settings.json()["settings"]["health_section_enabled"] is False
        assert settings.json()["settings"]["comment_display_limit"] == 12
        assert settings.json()["settings"]["danmaku_replay_count"] == 3
        assert settings.json()["settings"]["danmaku_replay_interval"] == 45
        assert settings.json()["settings"]["page_name"] == "Codex"
        assert settings.json()["settings"]["page_title"] == "Codex Status"
        assert settings.json()["settings"]["social_links"][0]["platform"] == "github"
        assert settings.json()["settings"]["social_links"][1]["url"] == "mailto:codex@example.com"
        assert settings.json()["settings"]["online_status_desc"] == "现在可以联系我。"
        assert settings.json()["settings"]["offline_status_desc"] == "现在暂时无法联系。"
        assert settings.json()["settings"]["music_library"] == str((tmp_path / "music").resolve())
        assert client.get("/api/status/query").json()["visit_metric"]["mode"] == "monthly"
        assert "Codex's" in client.get("/").text
        assert 'id="health-overview" aria-labelledby="health-overview-title"\n    hidden>' in client.get("/").text
        assert "https://github.com/univers629" in client.get("/").text
        assert "<title>Codex Status</title>" in client.get("/").text
        assert "<title>Codex Status · 详情</title>" in client.get("/details").text
        client.post("/panel/logout")
        assert "<title>Codex Status - 登录</title>" in client.get("/panel/login").text
        client.post("/panel/auth", json={"secret": "test-secret-1234"})
        assert client.get("/api/comments/query").json()["danmaku_enabled"] is False
        comment_settings = client.get("/api/comments/query", params={"limit": 50}).json()
        assert comment_settings["comment_display_limit"] == 12
        assert len(comment_settings["comments"]) <= 12
        status_list = client.get("/api/status/list").json()["status_list"]
        assert status_list[0]["desc"] == "现在可以联系我。"
        assert status_list[1]["desc"] == "现在暂时无法联系。"

        profile = client.post(
            "/api/admin/device/profile",
            json={
                "id": "editable-device",
                "display_name": "书房电脑",
                "icon_key": "laptop",
                "sort_order": -5,
                "public": False,
            },
        )
        assert profile.status_code == 200
        assert profile.json()["device"]["show_name"] == "书房电脑"
        assert "editable-device" not in client.get("/api/status/query").json()["device"]

        snapshot = client.get("/api/admin/snapshot").json()
        saved = snapshot["devices"]["editable-device"]
        assert saved["profile"]["icon_key"] == "laptop"
        assert saved["profile"]["public"] is False

        client.post(
            "/api/device/set",
            json={
                "id": "editable-device",
                "show_name": "Overwritten By Client",
                "using": True,
                "status": "Browser",
            },
        )
        visible = client.post(
            "/api/admin/device/profile",
            json={
                "id": "editable-device",
                "display_name": "书房电脑",
                "icon_key": "laptop",
                "sort_order": -5,
                "public": True,
            },
        )
        assert visible.status_code == 200
        public_device = client.get("/api/status/query").json()["device"]["editable-device"]
        assert public_device["show_name"] == "书房电脑"
        assert public_device["profile"]["icon_key"] == "laptop"

        client.post(
            "/api/admin/settings",
            json={
                "visit_display_mode": "total",
                "danmaku_enabled": True,
                "health_section_enabled": True,
                "comment_display_limit": 8,
                "danmaku_replay_count": 1,
                "danmaku_replay_interval": 30,
                "page_name": main.c.page.name,
                "social_links": [],
                "music_library": main.c.main.music_library,
            },
        )
        assert client.get("/api/status/query").json()["visit_metric"]["label"] == "已被视奸"
        client.post("/api/device/remove", json={"id": "editable-device"})


def test_admin_uses_signed_session_and_post_actions():
    with TestClient(main.app) as client:
        login_page = client.get("/panel/login")
        assert login_page.status_code == 200
        assert login_page.headers["cache-control"] == "no-store"
        assert login_page.headers["referrer-policy"] == "no-referrer"
        assert "color-mode.css" in login_page.text
        assert "color-mode.js" in login_page.text
        assert 'id="color-mode-toggle"' in login_page.text
        assert 'class="login-card"' in login_page.text

        login = client.post(
            "/panel/auth",
            json={"secret": "test-secret-1234"},
        )
        assert login.status_code == 200
        token = client.cookies.get("alive-session")
        assert token
        assert "test-secret-1234" not in token


        panel = client.get("/panel")
        assert panel.status_code == 200
        assert "color-mode.css" in panel.text
        assert "color-mode.js" in panel.text
        assert "glass-select.css" in panel.text
        assert "glass-select.js" in panel.text
        assert 'id="color-mode-toggle"' in panel.text
        assert "ALIVE CONTROL CENTER" in panel.text
        assert 'data-loading="true" aria-busy="true"' in panel.text
        assert 'id="panel-loading-status"' in panel.text
        assert 'class="device-table-wrap"' in panel.text
        assert 'id="music-account-status"' not in panel.text
        assert 'id="music-credential-value"' not in panel.text
        assert 'id="new-secret"' in panel.text
        assert "test-secret-1234" not in panel.text
        assert '<a class="btn btn-secondary" href="/">查看前台</a>' in panel.text
        panel_css = client.get("/static/panel.css").text
        assert ".panel-header {" in panel_css
        assert "background: transparent;" in panel_css
        assert ".device-table-wrap::-webkit-scrollbar-track {" in panel_css
        assert "scrollbar-color:" in panel_css
        assert 'body.admin-panel[data-loading="true"] .panel-card' in panel_css
        panel_js = client.get("/static/panel.js").text
        assert "const [statusResponse, queryResponse] = await Promise.all([" in panel_js
        assert "window.onload = initPage" not in panel_js
        assert "void initPage();" in panel_js

        verify = client.post("/panel/verify", json={})
        assert verify.status_code == 200
        assert client.get("/panel/verify").status_code == 405

        status = client.post("/api/status/set", json={"status": 1})
        assert status.status_code == 200
        assert status.json()["set_to"] == 1

        logout = client.post("/panel/logout", json={})
        assert logout.status_code == 200
        assert client.get("/panel", follow_redirects=False).status_code == 302


def test_secret_in_query_string_is_not_accepted():
    with TestClient(main.app) as client:
        response = client.post(
            "/api/device/clear?secret=test-secret-1234",
            json={},
        )
        assert response.status_code == 401


def test_admin_favicon_upload_validates_and_writes_64px_ico(tmp_path, monkeypatch):
    favicon_path = tmp_path / "public" / "favicon.ico"
    monkeypatch.setattr(main, "FAVICON_PATH", favicon_path)
    headers = {"Authorization": "Bearer test-secret-1234"}

    def image_bytes(fmt, size):
        mode = "RGB" if fmt == "JPEG" else "RGBA"
        image = Image.new(mode, size, (24, 120, 220, 255))
        stream = io.BytesIO()
        image.save(stream, format=fmt)
        return stream.getvalue()

    with TestClient(main.app) as client:
        valid = client.post(
            "/api/admin/favicon",
            headers=headers,
            content=image_bytes("PNG", (96, 96)),
        )
        assert valid.status_code == 200
        assert valid.json()["favicon"].startswith("/favicon.ico?v=")
        assert favicon_path.is_file()
        with Image.open(favicon_path) as output:
            assert output.format == "ICO"
            assert output.size == (64, 64)
            assert output.mode == "RGBA"
        served = client.get("/favicon.ico")
        assert served.status_code == 200
        assert served.content == favicon_path.read_bytes()
        assert served.headers["cache-control"] == "no-cache"
        assert client.get("/favicon.ico?v=changed").headers["cache-control"] == "public, max-age=31536000, immutable"

        nonsquare = client.post(
            "/api/admin/favicon",
            headers=headers,
            content=image_bytes("JPEG", (64, 32)),
        )
        assert nonsquare.status_code == 400
        assert "square" in nonsquare.json()["message"]

        svg = client.post(
            "/api/admin/favicon",
            headers=headers,
            content=b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
        )
        assert svg.status_code == 415

        oversize = client.post(
            "/api/admin/favicon",
            headers=headers,
            content=b"x" * (5 * 1024 * 1024 + 1),
        )
        assert oversize.status_code == 413


def test_admin_profile_avatar_generates_avatar_favicon_and_validates_social_links(tmp_path, monkeypatch):
    avatar_path = tmp_path / "public" / "profile-avatar.webp"
    favicon_path = tmp_path / "public" / "favicon.ico"
    monkeypatch.setattr(main, "PROFILE_AVATAR_PATH", avatar_path)
    monkeypatch.setattr(main, "FAVICON_PATH", favicon_path)

    image = Image.new("RGB", (240, 120), (120, 60, 220))
    stream = io.BytesIO()
    image.save(stream, format="JPEG")
    headers = {"Authorization": "Bearer test-secret-1234"}

    with TestClient(main.app) as client:
        uploaded = client.post(
            "/api/admin/profile/avatar",
            headers=headers,
            content=stream.getvalue(),
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["profile_avatar"].startswith("/profile-avatar.webp?v=")
        assert uploaded.json()["favicon"].startswith("/favicon.ico?v=")
        with Image.open(avatar_path) as avatar:
            assert avatar.format == "WEBP"
            assert avatar.size == (512, 512)
        with Image.open(favicon_path) as favicon:
            assert favicon.format == "ICO"
            assert favicon.size == (64, 64)
        saved = client.post(
            "/api/admin/settings",
            headers=headers,
            json={
                "social_links": [
                    {"platform": "bilibili", "url": "https://space.bilibili.com/123"},
                    {"platform": "email", "url": "alive@example.com"},
                ]
            },
        )
        assert saved.status_code == 200
        assert [item["platform"] for item in saved.json()["settings"]["social_links"]] == ["bilibili", "email"]
        assert "mailto:alive@example.com" in client.get("/").text
        assert client.post(
            "/api/admin/settings",
            headers=headers,
            json={"social_links": [{"platform": "github", "url": "javascript:alert(1)"}]},
        ).status_code == 400


def test_admin_can_rotate_secret_without_echoing_it(tmp_path):
    original_path = main.SECRET_OVERRIDE_FILE
    original_secret = main.c.main.secret
    main.SECRET_OVERRIDE_FILE = tmp_path / "admin-secret"
    try:
        with TestClient(main.app) as client:
            client.post("/panel/auth", json={"secret": original_secret})
            rotated = client.post(
                "/api/admin/secret",
                json={"new_secret": "new-test-secret-5678"},
            )
            assert rotated.status_code == 200
            assert "new-test-secret-5678" not in rotated.text
            assert rotated.headers["cache-control"] == "no-store"
            assert main.SECRET_OVERRIDE_FILE.read_text(encoding="utf-8") == "new-test-secret-5678"
            client.cookies.clear()
            assert client.post(
                "/panel/verify",
                headers={"Authorization": f"Bearer {original_secret}"},
                json={},
            ).status_code == 401
            assert client.post(
                "/panel/verify",
                headers={"Authorization": "Bearer new-test-secret-5678"},
                json={},
            ).status_code == 200
    finally:
        main.c.main.secret = original_secret
        main.SECRET_OVERRIDE_FILE = original_path

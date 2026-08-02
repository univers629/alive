import sqlite3
from time import time

from fastapi_data import Data, _CommentData, _DeviceStatusData, _MusicStateData
from models import ConfigModel


def test_metrics_total_survives_database_reopen(tmp_path):
    database = tmp_path / "alive.db"
    config = ConfigModel()
    config.main.database = f"sqlite:///{database.as_posix()}"
    config.metrics.enabled = True

    first = Data(config, start_scheduler=False)
    first.record_metrics("/", count=321)
    first.close()

    reopened = Data(config, start_scheduler=False)
    try:
        assert reopened.metrics_resp["total"]["/"] == 321
    finally:
        reopened.close()


def test_runtime_site_settings_survive_database_reopen(tmp_path):
    database = tmp_path / "alive.db"
    config = ConfigModel()
    config.main.database = f"sqlite:///{database.as_posix()}"

    first = Data(config, start_scheduler=False)
    assert first.card_style == "glass"
    first.set_runtime_setting("danmaku_enabled", "false")
    first.set_runtime_setting("page_name", "RealDeviceOwner")
    first.set_runtime_setting("page_title", "Real Device Status")
    first.set_runtime_setting("card_style", "solid")
    first.set_runtime_setting("online_status_desc", "Available now")
    first.set_runtime_setting("offline_status_desc", "Unavailable now")
    first.set_runtime_setting("music_library", str(tmp_path / "music"))
    first.close()

    reopened = Data(config, start_scheduler=False)
    try:
        assert reopened.danmaku_enabled is False
        assert reopened.page_name == "RealDeviceOwner"
        assert reopened.page_title == "Real Device Status"
        assert reopened.card_style == "solid"
        assert reopened.online_status_desc == "Available now"
        assert reopened.offline_status_desc == "Unavailable now"
        assert reopened.music_library == str(tmp_path / "music")
    finally:
        reopened.close()


def test_stale_device_is_marked_not_using(tmp_path):
    database = tmp_path / "alive.db"
    config = ConfigModel()
    config.main.database = f"sqlite:///{database.as_posix()}"
    config.status.device_timeout = 10

    data = Data(config, start_scheduler=False)
    try:
        data.device_set(
            id="desktop",
            show_name="Desktop",
            using=True,
            status="Editor",
        )
        with data.session() as session:
            device = session.get(_DeviceStatusData, "desktop")
            device.last_updated = time() - 11

        assert data._expire_devices() == 1
        assert data.device_list["desktop"]["using"] is False
        assert data.device_list["desktop"]["status"] == config.status.not_using
    finally:
        data.close()


def test_music_state_survives_database_reopen_and_respects_privacy(tmp_path):
    database = tmp_path / "alive.db"
    music_library = tmp_path / "music"
    music_library.mkdir()
    track = music_library / "artist-song.flac"
    track.write_bytes(b"test audio")
    config = ConfigModel()
    config.main.database = f"sqlite:///{database.as_posix()}"
    config.main.music_library = str(music_library)

    first = Data(config, start_scheduler=False)
    first.music_set(
        {
            "device_id": "phone",
            "title": "本地歌曲",
            "artist": "测试歌手",
            "player_name": "Windows 媒体播放器",
            "player_icon": "media-player",
            "player_icon_url": "/music-player-icons/abc.png",
            "library_path": track.name,
            "duration": 120,
            "position": 5,
            "playing": True,
            "lyrics": [
                {"time": 8, "text": "后一句", "translation": ""},
                {"time": 0, "text": "先一句", "translation": ""},
            ],
        }
    )
    first.close()

    reopened = Data(config, start_scheduler=False)
    try:
        assert reopened.music_state["active"] is True
        assert reopened.music_state["title"] == "本地歌曲"
        assert reopened.music_state["player_name"] == "Windows 媒体播放器"
        assert reopened.music_state["player_icon_url"] == "/music-player-icons/abc.png"
        assert reopened.music_state["lyrics"][0]["text"] == "先一句"
        audio_url = reopened.music_state["audio_url"]
        assert audio_url.startswith("/api/music/audio/")
        assert reopened.music_audio_path(audio_url.rsplit("/", 1)[-1]) == track
        reopened.private_mode = True
        assert reopened.music_state["active"] is True
        assert reopened.music_audio_path(audio_url.rsplit("/", 1)[-1]) == track
    finally:
        reopened.close()


def test_netease_stream_never_uses_alive_local_audio(tmp_path):
    music_library = tmp_path / "music"
    unrelated = music_library / "netease" / "33894312.mp3"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_bytes(b"ID3cached")
    config = ConfigModel()
    config.main.database = "sqlite:///:memory:"
    config.main.music_library = str(music_library)
    data = Data(config, start_scheduler=False)
    try:
        state = data.music_set(
            {
                "source_mode": "netease-api",
                "source_id": "33894312",
                "title": "网易云歌曲",
                "audio_url": "https://example.test/temporary",
                "library_path": "netease/33894312.mp3",
                "duration": 120,
                "position": 5,
                "playing": True,
            }
        )
        assert state["source_mode"] == "netease-api"
        public = data.music_state
        assert public["source_mode"] == "netease-api"
        assert public["audio_url"] == "https://example.test/temporary"
        assert data.music_audio_path("not-a-local-token") is None
    finally:
        data.close()


def test_playing_music_stores_reported_position_without_correction(tmp_path):
    config = ConfigModel()
    config.main.database = "sqlite:///:memory:"
    data = Data(config, start_scheduler=False)
    payload = {
        "title": "循环歌曲",
        "artist": "测试歌手",
        "duration": 230,
        "position": 228,
        "playing": True,
    }
    try:
        data.music_set(payload)
        with data.session() as session:
            session.get(_MusicStateData, 0).updated_at = time() - 5

        state = data.music_set({**payload, "position": 230})

        assert state["position"] == 230
    finally:
        data.close()


def test_health_state_survives_database_reopen_and_respects_privacy(tmp_path):
    database = tmp_path / "alive.db"
    config = ConfigModel()
    config.main.database = f"sqlite:///{database.as_posix()}"

    first = Data(config, start_scheduler=False)
    first.health_set(
        {
            "heart_rate": 72,
            "resting_heart_rate": 60,
            "steps": 4321,
            "step_goal": 8000,
            "source": "Health Connect",
        }
    )
    first.close()

    reopened = Data(config, start_scheduler=False)
    try:
        assert reopened.health_state["active"] is True
        assert reopened.health_state["heart_rate"] == 72
        assert reopened.health_state["steps"] == 4321
        reopened.private_mode = True
        assert reopened.health_state["active"] is True
    finally:
        reopened.close()


def test_admin_settings_and_device_profile_survive_reopen(tmp_path):
    database = tmp_path / "alive.db"
    config = ConfigModel()
    config.main.database = f"sqlite:///{database.as_posix()}"

    first = Data(config, start_scheduler=False)
    first.device_set(
        id="desktop",
        show_name="Client Name",
        using=True,
        status="Editor",
    )
    first.device_profile_set(
        id="desktop",
        display_name="后台名称",
        icon_key="server",
        sort_order=7,
        is_public=True,
    )
    first.visit_display_mode = "daily"
    first.close()

    reopened = Data(config, start_scheduler=False)
    try:
        device = reopened.device_list["desktop"]
        assert device["show_name"] == "后台名称"
        assert device["profile"]["icon_key"] == "server"
        assert reopened.visit_display_mode == "daily"
        assert reopened.public_visit_metric["mode"] == "daily"
    finally:
        reopened.close()


def test_comment_flags_migrate_and_survive_reopen(tmp_path):
    database = tmp_path / "alive.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE comments (id INTEGER PRIMARY KEY AUTOINCREMENT, nickname VARCHAR(24) NOT NULL, content VARCHAR(160) NOT NULL, color VARCHAR(16) NOT NULL, visitor_hash VARCHAR(64) NOT NULL, created_at FLOAT NOT NULL)")
    connection.execute("INSERT INTO comments (nickname, content, color, visitor_hash, created_at) VALUES ('旧评论', '保留内容', 'violet', 'hash', 1)")
    connection.commit()
    connection.close()
    config = ConfigModel()
    config.main.database = f"sqlite:///{database.as_posix()}"
    data = Data(config, start_scheduler=False)
    try:
        comment = data.comment_list(10)[0]
        assert comment["favorite"] is False
        assert comment["pinned"] is False
        updated = data.comment_update(comment["id"], True, True)
        assert updated["favorite"] is True
        assert updated["pinned"] is True
    finally:
        data.close()
    reopened = Data(config, start_scheduler=False)
    try:
        assert reopened.comment_admin_list()[0]["pinned"] is True
    finally:
        reopened.close()


def test_music_player_icon_url_migrates_on_old_database(tmp_path):
    database = tmp_path / "alive.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE music_player_meta (id INTEGER PRIMARY KEY NOT NULL, player_name VARCHAR(200) NOT NULL, player_icon VARCHAR(64) NOT NULL, library_path TEXT NOT NULL)")
    connection.execute("INSERT INTO music_player_meta (id, player_name, player_icon, library_path) VALUES (0, '旧播放器', 'media-player', '')")
    connection.commit()
    connection.close()
    config = ConfigModel()
    config.main.database = f"sqlite:///{database.as_posix()}"
    data = Data(config, start_scheduler=False)
    try:
        columns = {
            row[1]
            for row in sqlite3.connect(database)
            .execute("PRAGMA table_info(music_player_meta)")
            .fetchall()
        }
        assert "player_icon_url" in columns
        assert data.music_state["player_icon_url"] == ""
        stored = data.music_set(
            {
                "title": "迁移后的歌曲",
                "player_icon_url": "/music-player-icons/def.png",
            }
        )
        assert stored["player_icon_url"] == "/music-player-icons/def.png"
    finally:
        data.close()


def test_device_reorder_swaps_adjacent_and_normalizes_profiles():
    config = ConfigModel()
    config.main.database = "sqlite:///:memory:"
    data = Data(config, start_scheduler=False)
    try:
        for device_id in ("a", "b", "c"):
            data.device_set(id=device_id, show_name=device_id.upper())
        result = data.device_reorder("b", "down")
        assert list(result) == ["a", "c", "b"]
        assert [item["profile"]["sort_order"] for item in result.values()] == [0, 1, 2]
        assert list(data.device_reorder("a", "up")) == ["a", "c", "b"]
    finally:
        data.close()

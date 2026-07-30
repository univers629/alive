from time import time

from fastapi_data import Data, _DeviceStatusData
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
    first.set_runtime_setting("danmaku_enabled", "false")
    first.set_runtime_setting("page_name", "RealDeviceOwner")
    first.set_runtime_setting("music_library", str(tmp_path / "music"))
    first.close()

    reopened = Data(config, start_scheduler=False)
    try:
        assert reopened.danmaku_enabled is False
        assert reopened.page_name == "RealDeviceOwner"
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
        assert reopened.music_state["lyrics"][0]["text"] == "先一句"
        audio_url = reopened.music_state["audio_url"]
        assert audio_url.startswith("/api/music/audio/")
        assert reopened.music_audio_path(audio_url.rsplit("/", 1)[-1]) == track
        reopened.private_mode = True
        assert reopened.music_state["active"] is False
        assert reopened.music_audio_path(audio_url.rsplit("/", 1)[-1]) is None
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
        assert reopened.health_state["active"] is False
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

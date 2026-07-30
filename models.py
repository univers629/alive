# coding: utf-8

from typing import Literal

from pydantic import BaseModel, Field, PositiveInt

# ========== 用户配置开始 ==========


class _StatusItemModel(BaseModel):
    '''
    状态列表设置 (`status.status_list`) 中的项
    '''

    id: int = -1
    '''
    状态索引 (id)
    - *应由 `config.Config.__init__()` 动态设置*
    '''

    name: str
    '''
    `status.status_list[*].name`
    状态名称
    '''

    desc: str
    '''
    `status.status_list[*].desc`
    状态描述
    '''

    color: str = 'awake'
    '''
    `status.status_list[*].color`
    状态颜色 \n
    对应 `static/style.css` 中的 `.sleeping` `.awake` 等类 (可自行前往修改)
    '''


class MusicLyricLineModel(BaseModel):
    """A timestamped lyric line sent by a trusted Alive client."""

    time: float = Field(ge=0, le=86400)
    text: str = Field(default='', max_length=500)
    translation: str = Field(default='', max_length=500)


class MusicStateUpdateModel(BaseModel):
    """The complete now-playing state accepted by ``POST /api/music/set``."""

    source_mode: Literal[
        "metadata-only",
        "local-upload",
        "netease-api",
        "external-url",
    ] = "metadata-only"
    source_id: str = Field(default='', max_length=128)
    device_id: str = Field(default='', max_length=1024)
    title: str = Field(default='', max_length=300)
    artist: str = Field(default='', max_length=300)
    album: str = Field(default='', max_length=300)
    cover_url: str = Field(default='', max_length=4096)
    audio_url: str = Field(default='', max_length=4096)
    source_url: str = Field(default='', max_length=4096)
    player_name: str = Field(default='', max_length=200)
    player_icon: str = Field(default='media-player', max_length=64)
    library_path: str = Field(default='', max_length=4096)
    duration: float = Field(default=0, ge=0, le=86400)
    position: float = Field(default=0, ge=0, le=86400)
    playing: bool = False
    lyrics: list[MusicLyricLineModel] = Field(default_factory=list, max_length=5000)


class MusicTrackCheckModel(BaseModel):
    """Content identity used before a trusted client uploads one audio file."""

    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    suffix: Literal[".flac", ".mp3", ".m4a", ".wav", ".ogg", ".opus"]
    size: int = Field(gt=0)


class HealthStateUpdateModel(BaseModel):
    """Latest body-status snapshot reported by a trusted health client."""

    heart_rate: int | None = Field(default=None, ge=20, le=260)
    resting_heart_rate: int | None = Field(default=None, ge=20, le=260)
    heart_rate_min: int | None = Field(default=None, ge=20, le=260)
    heart_rate_max: int | None = Field(default=None, ge=20, le=260)
    steps: int | None = Field(default=None, ge=0, le=500_000)
    step_goal: int | None = Field(default=None, ge=1, le=500_000)
    source: str = Field(default="", max_length=120)
    measured_at: float | None = Field(default=None, ge=0)


class CommentCreateModel(BaseModel):
    """A public comment that can also be displayed as a danmaku message."""

    nickname: str = Field(default="", max_length=24)
    content: str = Field(min_length=1, max_length=160)
    color: Literal["violet", "cyan", "rose", "amber", "green"] = "violet"
    website: str = Field(default="", max_length=200)


class _MainConfigModel(BaseModel):
    '''
    系统基本配置 (`main`)
    '''

    database: str = 'sqlite:///../data/alive.db'
    '''
    数据库地址
    - SQLite: `sqlite:///../文件名.db`
    - MySQL: `mysql://用户名:密码@主机:端口号/数据库名`
    - 更多: https://docs.sqlalchemy.org.cn/en/20/core/engines.html#backend-specific-urls
    '''

    host: str = '0.0.0.0'
    '''
    `main.host`
    监听地址
    - ipv4: `0.0.0.0` 表示监听所有接口
    - ipv6: `::` 表示监听所有接口
    '''

    port: PositiveInt = 9010
    '''
    `main.port`
    服务监听端口 \n
    默认为 `9010`
    '''

    debug: bool = False
    '''
    `main.debug`
    是否启用调试日志与禁用资源缓存 \n
    (普通用户无需更改)
    '''

    log_file: str = ''
    '''
    `main.log_file`
    保存日志文件目录 (留空禁用) \n
    如: `data/running.log` \n
    **注意: 不会自动切割日志**
    '''

    colorful_log: bool = True
    '''
    控制控制台输出日志是否有颜色及 Emoji 图标
    - 如在获取控制台输出时遇到奇怪问题可关闭
    - 建议使用 `main.log_file` 来获取日志文件 (日志文件始终不带颜色 & Emoji)
    '''

    timezone: str = 'Asia/Shanghai'
    '''
    `main.timezone`
    控制网页 / API 返回中时间的时区 \n
    默认: `Asia/Shanghai` (北京时间)
    '''

    secret: str = ''
    '''
    `main.secret`
    密钥, 更新状态时需要 \n
    **请勿泄露, 相当于密码!!!**
    '''

    music_library: str = 'data/music-library'
    '''
    `main.music_library`
    由可信客户端按需上传的音乐存储目录。默认位于 Docker 持久化的
    `data/music-library`，不会依赖服务器本地存在 `D:\\Music`。
    只有当前系统媒体会话匹配到的歌曲才会通过“一起听”公开流式传输。
    '''

    music_upload_max_mb: PositiveInt = 200
    '''
    `main.music_upload_max_mb`
    单个音频文件允许上传的最大 MiB。上传采用流式落盘，不会把整首歌读入内存。
    '''

    music_session_timeout: int = 35
    '''
    `main.music_session_timeout`
    音乐上报器停止心跳后，当前音乐卡片及音频失效的秒数。
    '''

    netease_meting_api: str = 'https://api.qijieya.cn/meting/'
    '''
    `main.netease_meting_api`
    网易云歌曲 ID 的 Meting 兼容解析接口。Alive 只向此可信配置地址发送歌曲 ID，
    不会把全局上报密钥发送给第三方。
    '''

    netease_meting_fallback_api: str = 'https://musicapi.qijieya.cn/meting/'
    '''
    `main.netease_meting_fallback_api`
    主接口失败时尝试的备用 Meting 兼容接口；留空可禁用备用接口。
    '''

    netease_api_timeout: float = Field(default=8, ge=1, le=30)
    '''
    `main.netease_api_timeout`
    网易云第三方解析请求的超时秒数。
    '''

    health_session_timeout: int = 1800
    '''
    `main.health_session_timeout`
    身体状态超过此秒数没有更新时标记为非实时；数据仍保留用于展示。
    '''

    cache_age: int = 1200
    '''
    `main.cache_age`
    静态资源缓存时间 (秒)
    - *建议设置为 20 分钟 (1200s)*
    '''

    cors_origins: list[str] | str = '*'
    '''
    `main.cors_origins`
    允许跨域请求的域名
    - *默认为 `*` (允许所有域名)*
    '''

    https: bool = False
    '''
    `main.https`
    是否启用 https
    '''

    ssl_cert: str = 'data/cert.pem'
    '''
    `main.ssl_cert`
    ssl 证书路径
    '''

    ssl_key: str = 'data/key.pem'
    '''
    `main.ssl_key`
    ssl 密钥路径
    '''


class _PageConfigModel(BaseModel):
    '''
    页面内容配置 (`page`)
    '''

    name: str = 'User'
    '''
    `page.name`
    你的名字
    - 将显示在网页中的 `[User]'s Status:` 处
    '''

    title: str = f'{name} Alive?'
    '''
    `page.title`
    页面标题 (`<title>`)
    '''

    desc: str = f'{name} \'s Online Status Page'
    '''
    `page.desc`
    页面详情 (用于 SEO, 或许吧)
    - *`<meta name="description">`*
    '''
    favicon: str = '/favicon.ico'
    '''
    `page.favicon`
    页面图标 (favicon) url, 默认为 /favicon.ico
    - *可为绝对路径 / 相对路径 url*
    '''

    background: str = 'https://imgapi.siiway.top/image'
    '''
    `page.background`
    背景图片 url / api
    - *默认为 `https://imgapi.siiway.top/image` (https://github.com/siiway/imgapi)*
    '''

    learn_more_text: str = 'GitHub Repo'
    '''
    `page.learn_more_text`
    更多信息链接的提示
    - *默认为 `GitHub Repo`*
    '''

    learn_more_link: str = '/docs'
    '''
    `page.learn_more_link`
    更多信息链接的目标
    - *默认为本仓库链接*
    '''

    more_text: str = ''
    '''
    `page.more_text`
    内容将在状态页底部 learn_more 上方插入 (不转义)
    - *你可以在此中插入 统计代码 / 备案号 等信息*
    '''

    theme: str = 'default'
    '''
    `page.theme`
    设置页面的默认主题
    - 主题名即为 `theme/` 下的文件夹名
    '''

    auto_theme: bool = False
    '''
    是否根据浏览器的深色/浅色偏好自动选择主题
    '''

    light_theme: str = 'default'
    '''
    自动主题启用时使用的浅色主题
    '''

    dark_theme: str = 'default'
    '''
    自动主题启用时使用的深色主题
    '''


class _StatusConfigModel(BaseModel):
    '''
    状态配置 (`status`)
    '''

    device_slice: int = 50
    '''
    `status.device_slice`
    设备状态从开头截取多少文字显示 (防止窗口标题过长影响页面显示)
    - *设置为 0 禁用*
    '''

    refresh_interval: PositiveInt = 5000
    '''
    `status.refresh_interval`
    网页多久刷新一次状态 (毫秒) \n
    *仅在回退到原始轮询方式后使用*
    '''

    device_timeout: int = 150
    '''
    设备超过多少秒没有上报后，自动标记为未使用。
    - 默认 150 秒，应大于客户端心跳间隔
    - 设置为 0 可关闭服务端超时兜底
    '''

    not_using: str = '未在使用'
    '''
    `status.not_using`
    锁定设备未在使用时的提示 *(如为空则使用设备提交值)*
    '''

    sorted: bool = False
    '''
    `status.sorted`
    控制是否对设备进行排序 *(A-Z, 0-9)*
    '''

    using_first: bool = False
    '''
    `status.using_first`
    控制是否优先显示正在使用设备
    - 顺序: 在线 (正在使用 -> 未在使用) -> 离线 -> 未知
    '''

    status_list: list[_StatusItemModel] = [
        _StatusItemModel(
            name='活着',
            desc='目前在线，可以通过任何可用的联系方式联系本人。',
            color='awake'
        ),
        _StatusItemModel(
            name='似了',
            desc='睡似了或其他原因不在线，紧急情况请使用电话联系。',
            color='sleeping'
        )
    ]
    '''
    `status.status_list`
    手动设置的状态列表 \n
    *可自行设置, 但请确保至少有 0 和 1 两个状态*
    - *见 `_StatusItemModel`*
    '''


class _MetricsConfigModel(BaseModel):
    '''
    统计配置 (`metrics`)
    '''

    enabled: bool = True
    '''
    `metrics.enabled`
    是否启用统计功能
    '''

    allow_list: list[str] = [
        '/',
        '/api/status/query',
        '/api/status/list',
        '/api/status/set',
        '/api/device/set',
        '/api/device/remove',
        '/api/device/clear',
        '/api/device/private',
        '/api/status/events',
        '/api/metrics',
        '/api/meta',
        '/robots.txt',
        '/favicon.ico',
        '[static]'
    ]
    '''
    `metrics.allow_list`
    将计入统计的路径列表 \n
    *其中的 `[static]` 为特殊值, 匹配 static 目录中的所有文件*
    '''


class ConfigModel(BaseModel):
    '''
    用户配置文件 \n
    加载顺序:
    - `data/.env` & 环境变量
    - `data/config.yaml`
    - `data/config.toml`
    '''

    main: _MainConfigModel = _MainConfigModel()
    page: _PageConfigModel = _PageConfigModel()
    status: _StatusConfigModel = _StatusConfigModel()
    metrics: _MetricsConfigModel = _MetricsConfigModel()

# ========== 用户配置结束 ==========

env_vaildate_json_keys = [
    'status_status_list',
    'metrics_allow_list',
]
'''
此列表中的键将会尝试解析为 json
(不包含 `alive_`)
'''

# 配置

配置加载顺序为环境变量、`data/config.yaml`、`data/config.toml`、
`data/config.json`，后面的文件会覆盖前面的同名配置。Docker 推荐使用根目录
`.env` 给 Compose 传值；应用环境变量统一以 `ALIVE_` 开头。

## 最小配置

根目录 `.env`：

```dotenv
ALIVE_SECRET=change-me-at-least-6-characters
ALIVE_PAGE_NAME=YourName
ALIVE_MUSIC_LIBRARY_HOST=./data/music-library
```

Compose 会把密钥和用户名映射为应用环境变量，并把
`ALIVE_MUSIC_LIBRARY_HOST` 挂载到容器的 `/alive/music-library`。

直接运行 Python 时，可以在 `data/.env` 中写：

```dotenv
ALIVE_MAIN_SECRET=change-me-at-least-6-characters
ALIVE_PAGE_NAME=Alive
```

## YAML 示例

`data/config.yaml`：

```yaml
main:
  secret: change-me-at-least-6-characters
  host: 0.0.0.0
  port: 9010
  timezone: Asia/Shanghai
  cors_origins:
    - https://status.example.com

page:
  name: Alive
  title: Alive Status
  more_text: "累计访问 {visit_total} 次"
  auto_theme: false
  light_theme: default
  dark_theme: default

metrics:
  enabled: true
```

## 常用字段

- `main.database`：默认 `sqlite:///../data/alive.db`。
- `main.secret`：全站唯一的共享密钥，后台和所有设备客户端共用；最低 6 字符，
  不需要为每台设备设置不同密码。生产环境仍应使用随机长密钥。
- 后台轮换后的密钥保存在 `data/admin-secret`，优先于 Compose 初始密钥；接口和
  页面永远不会回显当前密钥。
- `main.music_library`：客户端按需上传的音频存储目录。Docker 默认使用
  `/alive/music-library`，宿主机目录由 `ALIVE_MUSIC_LIBRARY_HOST` 决定。
- `main.music_upload_max_mb`：单首音频上传上限，默认 200 MiB；上传过程流式落盘。
- `main.music_session_timeout`：音乐上报心跳失效秒数，默认 35。
- `main.netease_meting_api`：网易云歌曲 ID 的主 Meting 兼容解析地址，必须为
  HTTPS。服务端只发送歌曲 ID，不发送 Alive 密钥。
- `main.netease_meting_fallback_api`：主接口失败时的备用解析地址；留空可禁用。
- `main.netease_api_timeout`：第三方歌名、歌词和公开流入口解析超时，默认 8 秒。
  网易云音频由访客浏览器直接加载，不经过 Alive 存储。
- `main.health_session_timeout`：身体状态多久未更新后显示为非实时，默认 1800 秒。
- `main.cors_origins`：生产环境建议写明确来源，不要使用 `*`。
- `status.device_timeout`：设备心跳消失后自动标记为未使用的秒数，默认 150；
  设置为 0 可关闭。应大于客户端的心跳间隔。
- `main.https`、`main.ssl_cert`、`main.ssl_key`：直接由 Uvicorn 提供 HTTPS。
  使用反向代理时通常保持 `main.https: false`，由代理终止 TLS。
- `page.more_text`：支持 `{visit_daily}`、`{visit_weekly}`、
  `{visit_monthly}`、`{visit_yearly}`、`{visit_total}`。
- `metrics.enabled`：控制访问统计。统计存放在 SQLite 中。
- `metrics.allow_list`：只统计列出的路径，`[static]` 表示主题静态文件。

数组类型环境变量必须使用 JSON。例如：

```dotenv
ALIVE_MAIN_CORS_ORIGINS=["https://status.example.com"]
ALIVE_STATUS_STATUS_LIST=[{"name":"在线","desc":"可以联系","color":"awake"},{"name":"离线","desc":"暂时离开","color":"sleeping"}]
```

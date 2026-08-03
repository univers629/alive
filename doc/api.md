# Alive API

默认地址为 `http://localhost:9010`。中英双语说明位于 `/docs`，交互式
OpenAPI 页面位于 `/swagger`。

## 鉴权

所有写接口都需要密钥。推荐使用：

```http
Authorization: Bearer <ALIVE_SECRET>
```

Alive 只有一个全局 `ALIVE_SECRET`，后台和所有设备客户端共同使用。最低 6 位，
不需要也不会为每台设备生成独立密码；正式部署建议设置更长的随机值。

也支持 `Alive-Secret: <ALIVE_SECRET>` 请求头，以及 JSON body 中的 `secret`。
不要把密钥放在 URL、查询参数、日志或截图里。`?secret=...` 会被 Alive 拒绝。

浏览器管理后台在 `POST /panel/auth` 登录后得到一个签名的 `HttpOnly` Cookie。
Cookie 不包含原始密钥，并使用 `SameSite=Strict`；HTTPS 下还会设置 `Secure`。

## 路由总览

| 方法 | 路径 | 鉴权 | 用途 |
|---|---|---:|---|
| GET | `/` | 否 | 状态网页 |
| GET | `/api/meta` | 否 | 站点元数据 |
| GET | `/api/metrics` | 否 | 访问统计 |
| GET | `/api/status/query` | 否 | 当前状态和设备 |
| GET | `/api/status/list` | 否 | 可选手动状态 |
| GET | `/api/status/events` | 否 | SSE 状态更新流 |
| GET | `/api/health/query` | 否 | 当前心率和今日步数 |
| GET | `/api/music/query` | 否 | 当前音乐、进度和同步歌词 |
| GET | `/api/music/audio/{token}` | 否 | 收听当前已上传歌曲 |
| POST | `/api/status/set` | 是 | 修改手动状态 |
| POST | `/api/device/set` | 是 | 新增或更新设备 |
| POST | `/api/device/app-icon` | 是 | 上传 Android 当前应用图标 |
| POST | `/api/device/remove` | 是 | 删除设备 |
| POST | `/api/device/clear` | 是 | 清空设备 |
| POST | `/api/device/private` | 是 | 切换隐私模式 |
| POST | `/api/health/set` | 是 | 更新心率和今日步数 |
| POST | `/api/health/clear` | 是 | 清空身体状态 |
| POST | `/api/music/set` | 是 | 更新当前音乐和同步歌词 |
| POST | `/api/music/clear` | 是 | 清空当前音乐 |
| POST | `/api/music/cover` | 是 | 上传当前歌曲的内嵌封面 |
| POST | `/api/music/track/check` | 是 | 按哈希检查音频是否已保存 |
| POST | `/api/music/track/upload` | 是 | 流式上传当前播放的音频 |
| GET | `/api/admin/snapshot` | 会话/密钥 | 后台设备和展示设置 |
| GET | `/api/admin/music/library` | 会话/密钥 | 列出已上传音频及总占用 |
| POST | `/api/admin/music/library/delete` | 会话/密钥 | 删除选中的非当前音频 |
| POST | `/api/admin/settings` | 会话/密钥 | 修改主页、弹幕和音乐目录 |
| POST | `/api/admin/favicon` | 会话/密钥 | 上传 PNG、JPEG 或 WebP 网站图标 |
| POST | `/api/admin/secret` | 会话/密钥 | 轮换全局密钥 |
| POST | `/api/admin/device/profile` | 会话/密钥 | 修改设备显示资料 |
| POST | `/api/admin/device/reorder` | 会话/密钥 | 将设备与相邻设备交换并规范化顺序 |
| POST | `/api/admin/comments/remove` | 会话/密钥 | 删除一条评论 |
| POST | `/api/admin/comments/update` | 会话/密钥 | 修改评论收藏和置顶状态 |
| POST | `/api/admin/comments/clear` | 会话/密钥 | 清空所有评论 |
| GET | `/panel` | 会话 | 管理后台页面 |
| POST | `/panel/auth` | 密钥 | 登录后台 |
| POST | `/panel/verify` | 会话 | 验证后台会话 |
| POST | `/panel/logout` | 否 | 清除后台会话 |

对写路径发送 GET 会返回 `405 Method Not Allowed`。

## 写接口 JSON

### POST `/api/status/set`

```json
{"status": 1}
```

`status` 是 `/api/status/list` 返回的状态 id。

### POST `/api/device/set`

```json
{
  "id": "desktop",
  "show_name": "Desktop",
  "using": true,
  "status": "VS Code",
  "fields": {
    "battery": 80
  }
}
```

`id` 是稳定的设备标识；`show_name` 是显示名；`using` 是布尔值；`status`
是正在使用的应用或自定义描述；`fields` 是可选扩展对象。

### POST `/api/device/remove`

```json
{"id": "desktop"}
```

### POST `/api/device/clear`

发送空对象：

```json
{}
```

### POST `/api/device/private`

```json
{"private": true}
```

### POST `/api/health/set`

```json
{
  "heart_rate": 76,
  "resting_heart_rate": 61,
  "heart_rate_min": 55,
  "heart_rate_max": 128,
  "steps": 6248,
  "step_goal": 8000,
  "source": "Health Connect"
}
```

客户端可以只上报心率或只上报步数，服务端会保留上一份其他字段。身体状态保存在
SQLite；超过 `main.health_session_timeout` 后标记为非实时，但不会立即丢失。

### POST `/api/music/set`

```json
{
  "source_mode": "local-upload",
  "source_id": "",
  "device_id": "windows-desktop",
  "title": "歌曲名",
  "artist": "歌手",
  "album": "专辑",
  "cover_url": "https://example.com/cover.jpg",
  "audio_url": "",
  "source_url": "https://music.example.com/song/123",
  "player_name": "Windows 媒体播放器",
  "player_icon": "media-player",
  "library_path": "a1/a1...完整SHA256....flac",
  "duration": 210,
  "position": 36.5,
  "playing": true,
  "lyrics": [
    {"time": 0, "text": "第一句歌词"},
    {"time": 8.2, "text": "第二句歌词", "translation": "可选翻译"}
  ]
}
```

`position` 是上报时的播放秒数，服务端会记录上报时间；`playing=true` 时，
前端在两次上报之间自行推进进度并匹配歌词，不需要客户端每秒请求。暂停、切歌、
拖动进度时重新上报即可。

`player_name` 和 `player_icon` 用于卡片右侧播放器图标。`library_path` 应使用
`POST /api/music/track/check` 或 `/api/music/track/upload` 返回的值；服务端会为
当前歌曲生成短期可用的
`/api/music/audio/{token}` 地址。该地址只能访问当前上报的文件，不能枚举音乐
目录，停止心跳约 35 秒后失效。

当 `source_mode=local-upload` 且 `library_path` 有效时，服务端会在音频首次上传或
首次再次播放时读取文件标签。标签中的歌名、歌手、专辑、内嵌封面和带时间戳歌词
会写入音乐库索引并用于公开音乐状态，客户端不必再重复上传封面和歌词。

`audio_url` 仍可用于站长有权公开播放的外部音频；本地匹配生成的地址优先。
浏览器必须由访客主动点击“一起听”才会播放，且网页不能控制机主播放器。

`source_mode` 支持：

- `metadata-only`：只显示系统媒体会话信息；
- `local-upload`：播放由可信客户端上传并返回 `library_path` 的本地文件；
- `netease-api`：`source_id` 必须是网易云歌曲 ID。服务端解析歌名、封面、
  公开流媒体入口和 LRC，访客浏览器直接加载第三方流；
- `external-url`：站长自行提供有权公开的 `audio_url`。

`netease-api` 不需要客户端上传音频，也不接受网易云 Cookie。Alive 不代理、不
下载网易云音频；`/api/music/audio/{token}` 只服务可信客户端上传的本地文件。

### POST `/api/music/clear`

发送空对象：

```json
{}
```

### POST `/api/music/cover`

请求体直接发送 JPEG、PNG 或 WebP 二进制，最大 3 MiB，并在 Bearer 请求头中
携带密钥。响应返回内容寻址的公开封面 URL。该接口保留给不上传音频的旧客户端；
`local-upload` 音频的内嵌封面由服务端自动读取。

### POST `/api/music/track/check`

```json
{
  "sha256": "64位十六进制内容哈希",
  "suffix": ".flac",
  "size": 45678901
}
```

响应中的 `exists=true` 表示服务器已经保存相同内容，可以直接使用返回的
`library_path`，不必重复上传。

### POST `/api/music/track/upload`

请求体直接发送音频二进制，并携带以下请求头：

```http
Authorization: Bearer <ALIVE_SECRET>
Content-Length: <文件字节数>
X-Alive-Audio-Sha256: <64位内容哈希>
X-Alive-Audio-Suffix: .flac
```

支持 `.flac`、`.mp3`、`.m4a`、`.wav`、`.ogg` 和 `.opus`。服务端会流式写入
临时文件，验证大小、SHA-256 和容器文件头后再原子保存；不会把整首歌同时放入
服务器内存。默认单文件上限为 200 MiB。

可信客户端应在切歌时先用 `metadata-only` 发送可立即展示的元数据，再在后台上传
本地音频；上传成功后以相同的歌曲状态和返回的 `library_path` 再调用
`/api/music/set`。客户端可以对快速跳过的歌曲设置短暂的上传延迟；已开始的旧上传
可继续完成，但只有仍是当前歌曲的任务才能更新公开音乐状态。

### 音乐库后台管理

`GET /api/admin/music/library` 返回已上传音频的歌曲名、艺术家、专辑、哈希相对路径、
大小、修改时间和是否为当前播放文件。歌曲信息由服务端在上传完成或旧文件再次播放时
读取标签并写入 SQLite 索引；管理页不会在每次显示时重新扫描或解析全部音频。列表最多
返回 1000 个最新文件，但总数和总占用始终完整统计。

删除接口只接受音乐库内的受支持音频后缀，并且拒绝删除当前 `library_path`：

```json
{"paths": ["ab/ab...完整SHA256....flac"]}
```

切歌或调用 `POST /api/music/clear` 后，原当前文件才可在后台删除。接口不会接受
绝对路径或跳出音乐库的相对路径。

### 网易云公开流媒体

客户端以 `source_mode=netease-api` 调用 `POST /api/music/set` 时只发送歌曲 ID
和播放状态。服务端解析歌名、封面、歌词和公开流媒体入口，并通过公开音乐状态把
入口交给访客浏览器。访客直接连接第三方流媒体，Alive 不代理或保存网易云音频。

项目不提供网易云 Cookie、`MUSIC_U` 或账号 Token 的保存接口，也不尝试解锁会员
曲目或模拟官方多端同步。

### POST `/api/admin/settings`

```json
{
  "visit_display_mode": "monthly",
  "danmaku_enabled": true,
  "page_name": "YourName",
  "page_title": "Your Status",
  "music_library": "/alive/music-library"
}
```

允许值为 `total`、`daily`、`monthly`，分别表示累计、今日和本月。它只控制首页
展示，不会覆盖对应统计值。弹幕总开关、`Alive's Status:` 用户名和容器内音乐目录
同样持久化到 SQLite。`page_title` 必须为单行、非空且不超过 120 个字符；响应和后台
快照会返回当前带缓存版本的 `favicon` URL。

### POST `/api/admin/favicon`

请求体为原始 PNG、JPEG 或 WebP 图片，不使用 multipart。图片必须为 16 到 4096
像素范围内的正方形，且不超过 5 MiB。服务端会去除元数据、转换为 RGBA、缩放为
64x64，并原子写入持久化的 `data/public/favicon.ico`。

### POST `/api/admin/secret`

```json
{"new_secret": "replace-with-a-new-long-random-secret"}
```

密钥不会出现在响应中。轮换后旧会话和客户端密钥立即失效，新值保存在 Git 忽略的
`data/admin-secret`。公网使用时必须通过 HTTPS 登录和轮换。

### POST `/api/admin/device/profile`

```json
{
  "id": "desktop",
  "display_name": "书房电脑",
  "icon_key": "laptop",
  "public": true
}
```

`icon_key` 支持 `desktop`、`laptop`、`phone`、`tablet`、`watch`、`server`、
`game`、`other`、`bilibili`。设备资料独立于实时心跳数据；客户端继续上报 `show_name`
时，不会覆盖管理员已保存的 `display_name`。后台使用
`POST /api/admin/device/reorder` 携带 `{"id":"desktop","direction":"up"}`
进行相邻交换，`direction` 只能是 `up` 或 `down`；顶端上移和底端下移不会改变顺序。

### 后台评论管理

评论快照最多返回保留的 300 条评论，排序为置顶、收藏、最新。更新接口请求体为：

```json
{"id": 12, "favorite": true, "pinned": false}
```

评论响应公开返回 `favorite` 和 `pinned` 布尔值，但不会返回 `visitor_hash`。

## GET 是否会暴露密钥

GET 方法本身不会自动暴露密钥；问题出在把密钥写成
`/path?secret=xxx`。查询字符串可能进入浏览器历史、代理和服务器访问日志、
监控系统以及 `Referer`。Alive 的公开 GET 路由完全不需要密钥，写入一律 POST，
密钥应放在请求头中。即使使用 POST，也不要把密钥继续放在 URL。

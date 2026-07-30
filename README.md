# Alive

Alive 是一个用 FastAPI 编写的个人在线状态页。它提供公开状态页、设备上报 API、
浏览器管理后台、SQLite 持久化统计和 Docker 部署。

这是一个干净的新项目：

- 不包含 v4 路由、兼容插件或迁移脚本。
- 所有会改变数据的接口只接受 `POST`。
- 公开读取接口使用 `GET`，且不需要也不接受 URL 中的密钥。
- 管理后台仍可直接在浏览器中登录并修改状态、设备和隐私模式。
- 后台可选择首页展示累计、今日或本月访问数，并编辑设备名称、图标、顺序和公开状态。
- 后台可设置弹幕总开关、主页用户名和容器内音乐目录，并可安全轮换全局密钥。
- 弹幕区只保留最近 8 条留言；开启时每 30 秒只滚动一条。
- 首页设备使用响应式毛玻璃卡片；第二台设备以不同 `id` 上报后会自动增加卡片并多列排列。
- 首页累计访问次数保存在 `data/alive.db`，重启和更新容器后不会清零。

## Windows + Docker 快速开始

1. 复制环境变量示例：

   ```powershell
   Copy-Item .env.example .env
   ```

2. 编辑 `.env`，设置一个至少 6 位的全局 `ALIVE_SECRET`。后台和所有设备客户端
   共用这一项，不需要为每台设备分别设置密码；正式部署仍建议使用更长的随机值。

3. 启动：

   ```powershell
   docker compose up --build
   ```

4. 打开：

   - 状态页：<http://localhost:9010/>
   - 管理后台：<http://localhost:9010/panel>
   - 中英双语文档：<http://localhost:9010/docs>
   - FastAPI 交互测试：<http://localhost:9010/swagger>

数据库和上传封面通过 `./data:/alive/data` 持久化。`.env` 中的
`ALIVE_MUSIC_LIBRARY_HOST` 会挂载到容器的 `/alive/music-library`，用于保存
按需上传的本地音频；后台“容器内音乐目录”默认填写这个容器路径。Windows
上报器扫描哪个本机目录则由 `ALIVE_MUSIC_DIR` 单独决定。停止或重建容器不会
删除这些数据；不要手动删除 `data`，除非你确实想清空数据库和上传内容。

## 本机 Python 开发

需要 Python 3.10+，推荐安装 [uv](https://docs.astral.sh/uv/)：

```powershell
Copy-Item .env.example .env
uv sync
uv run pytest
uv run main.py
```

## API 示例

查询是公开的：

```powershell
curl.exe http://localhost:9010/api/status/query
```

上报必须使用 POST，推荐把密钥放在 `Authorization` 请求头：

```powershell
curl.exe -X POST http://localhost:9010/api/device/set `
  -H "Authorization: Bearer YOUR_LONG_RANDOM_SECRET" `
  -H "Content-Type: application/json" `
  -d '{\"id\":\"desktop\",\"show_name\":\"Desktop\",\"using\":true,\"status\":\"VS Code\"}'
```

完整接口见 [API 文档](doc/api.md)，配置见 [配置文档](doc/config.md)。

## Windows 当前音乐与“一起听”

音乐悬浮卡片的折叠状态只显示左侧圆形封面、中间一行歌名和下一行艺术家、
右侧播放器应用图标。点击卡片会同时向两侧和上下展开，只显示机主的只读进度、
一行当前歌词及“一起听”；没有可拖动进度条、播放控制和完整歌词滚动菜单。

上报器同时支持两种来源：

- 本地播放器：根据 Windows 媒体会话中的信息，在 `ALIVE_MUSIC_DIR` 的文件名和内嵌标签
  中定位当前音频并上传；歌名、歌手、专辑、时长和封面优先使用本地文件标签。
- 网易云 Windows 客户端：从本地 `webdb.dat` 或 `cloudmusic.elog` 取得歌曲 ID，
  由 Alive 获取歌名、封面、LRC 和公开流入口。访客浏览器直接加载第三方流，
  Alive 不下载音频，也不上传网易云客户端的本地缓存文件。

先播放一首歌，再在项目根目录运行：

```powershell
py -m pip install -r client\requirements-windows.txt
py client/win_media_session_reporter.py
```

本地文件支持 FLAC、MP3、M4A、Ogg/Opus 和 WAV。客户端先按 SHA-256 查重，
缺少时才流式上传，同一文件以后不会重复上传。文件名应包含系统显示的歌曲名；
若文件名比较特殊，可用 `--file` 明确指定当前音频：

```powershell
py client/win_media_session_reporter.py --once --file "C:\Music\某首歌.flac"
```

客户端每 10 秒发送一次播放进度心跳。要保持实时状态，需要让这个 PowerShell
窗口和播放器继续运行。按 `Ctrl+C` 或关闭窗口不会停止播放器，音乐卡片及临时
播放地址会在约 35 秒没有心跳后自动失效。

网易云桌面版的 elog 不会每秒写入播放位置。客户端会从最近一次真实位置开始使用
连续时钟估算，只有新的播放、暂停或跳转事件才重设基准；不会在每次 10 秒心跳时
重复读取旧的低进度，避免网页播放十几秒后又从头开始。

只上报一次用于本地测试：

```powershell
py client/win_media_session_reporter.py --once
```

清除当前音乐：

```powershell
py client/win_media_session_reporter.py --clear
```

旧版 Windows Media Player 在部分 Windows 版本上不注册系统媒体会话，本机测试
也无法读取；请优先使用 Windows 11 的“媒体播放器”（原 Groove 音乐应用包）。
本地歌曲不会整批上传：客户端只上传机主实际播放且成功匹配的当前文件，音频以
内容哈希命名保存在 `data/music-library`。只有这条本地上传链路会读取内嵌标签：
歌名、歌手、专辑、时长和封面优先采用本地音频文件中的信息，Windows 媒体会话
作为后备。

网易云链路只上报歌曲 ID、播放状态和位置。Alive 获取歌名、封面、歌词及稳定的
公开流媒体入口后，把入口交给访客浏览器；浏览器再直接连接解析服务/音乐 CDN，
网易云音频字节不经过 Alive，也不会保存到 `data/music-library`。因此切歌时不必
等待整首下载完成，带宽主要由每位访客和流媒体来源承担。
代价是访客的 IP、浏览器信息和请求时间会直接暴露给所配置的第三方解析服务/CDN；
部署公开站点时应在隐私说明中告知访客。

Alive 不接受、不保存也不转发 `MUSIC_U`、网易云 Cookie 或账号 Token，不尝试
会员曲目解锁，也不模拟网易云官方的多端播放同步。第三方解析服务的稳定性、公开
曲目可用性和版权不由 Alive 保证；公开流不可用时只展示歌曲状态。

访客点击一次“一起听”后，该页面会保持同听意图；机主切歌或短暂无音源时不会
自动退出，下一首流媒体可用后会继续播放，不需要反复点击。访客无法控制或拖动
机主播放器。普通时间偏差会通过约
`0.92–1.08` 的轻微变速平滑追赶，并在同步后恢复 `1.00`；只有机主真实拖动超过
约 12 秒时才会重新定位，避免周期性跳秒和断音。

## 身体状态

首页身体状态固定为两张卡：心率和今日步数。没有真实数据时只显示“等待真机上报”，
不会生成或展示虚构数值；
接入健康客户端后使用 Bearer 密钥调用 `POST /api/health/set`，页面会通过现有
SSE 自动切换为实时数据。身体状态同样保存在 SQLite，并受全站隐私模式控制。

如果点击“一起听”没有声音：

1. 确认机主的媒体播放器当前不是暂停状态；
2. 按 `Ctrl+F5` 强制刷新，确保加载最新播放器脚本；
3. 检查浏览器地址栏的“声音”权限，以及 Windows 音量合成器中浏览器是否静音；
4. 使用 Chrome、Edge 等正常浏览器测试。Codex 的嵌入式预览浏览器会禁止音频
   输出，但不影响普通浏览器。

## 后台展示和设备管理

打开 <http://localhost:9010/panel> 后：

- “前台访问次数展示”可选择累计访问、今日访问或本月访问；这只改变首页显示，
  不会清空任何统计。
- “设备管理”可修改显示名称、设备图标和排序，或关闭“公开”暂时从首页隐藏设备。
- 管理员资料与客户端实时状态分开保存，客户端下一次心跳不会覆盖后台名称和图标。
- “主页展示与弹幕”可修改 `Alive's Status:` 中的 `Alive`、弹幕总开关、访问次数
  周期和容器内音乐目录。
- “后台密钥”只接受两次新密钥输入，服务端从不把现有密钥回显给浏览器。轮换后
  旧会话与客户端密钥立即失效，新密钥保存在被 Git 忽略的 `data/admin-secret`。

登录密钥通过 HTTPS 下的 POST JSON 正文传输，不进入 URL、浏览器历史或访问日志。
登录成功后只保存 `HttpOnly`、`SameSite=Strict` 会话 Cookie；登录和密钥响应使用
`Cache-Control: no-store` 与 `Referrer-Policy: no-referrer`。公网部署必须在
Alive 前面配置 HTTPS 反向代理，HTTP 本身不能保护网络链路中的密码。

## 关于 FastAPI 重构

FastAPI 本身不是“功能更少”的版本。对 Alive 来说，它带来了自动 OpenAPI 文档、
清晰的请求校验、异步 SSE 和更直接的类型约束。真正决定安全性的仍然是接口设计：
因此本项目把读取和写入分开，所有写入只用 POST，并禁止把密钥放进查询字符串。

## 来源与许可证

Alive 基于 [sleepy-project/sleepy](https://github.com/sleepy-project/sleepy) 的前端、
客户端思路与部分实现重构而来，并保留上游 MIT 许可及版权声明。Alive 不再提供上游
v4 兼容层；需要旧数据时，请在旧项目中自行归档，而不是把迁移逻辑带进本项目。

详见 [LICENSE](LICENSE)。

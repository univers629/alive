# Alive

一个用 FastAPI 编写的个人在线状态页，提供公开状态页、设备与音乐上报 API、浏览器管理后台和 SQLite 持久化存储。

## 首次 Docker 部署

在项目目录执行：

```bash
cp .env.example .env
nano .env
```

`.env` 中必须填写：

| 变量 | 说明 |
| --- | --- |
| `ALIVE_SECRET` | 全局密钥，至少 6 位。后台登录和所有上报客户端使用同一个值，建议使用长随机字符串。 |
| `ALIVE_PAGE_NAME` | 首页展示的用户名。 |

服务器可选变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ALIVE_PORT` | `9010` | Docker 对外端口，也是容器内 Alive 监听端口。 |
| `ALIVE_MUSIC_LIBRARY_HOST` | `./data/music-library` | 宿主机音乐库目录，挂载到容器内 `/alive/music-library`。请填写服务器上的实际绝对路径或相对项目目录的路径。 |

例如：

```env
ALIVE_PORT=18010
ALIVE_MUSIC_LIBRARY_HOST=/srv/alive/music-library
```

然后构建并启动：

```bash
sudo docker compose up -d --build
```

反向代理时，将域名转发到 `127.0.0.1:ALIVE_PORT`。未设置 `ALIVE_PORT` 时即为 `127.0.0.1:9010`。

## 音乐的两条线路

### 网易云在线流媒体

上报 `source_mode=netease-api` 和网易云歌曲 ID 后，Alive 通过现有网易云解析链路取得在线 `audio_url`、封面与歌词。此链路不下载音乐文件，不写入 `ALIVE_MUSIC_LIBRARY_HOST`，也不经过本地压缩缓存。

### 本地播放器上报与同听

任意支持 Alive 本地上报协议的本地播放器插件或客户端均可使用。它会先立即上报歌名、艺术家和歌词，随后按配置决定是否上传当前本地音乐文件。

- 插件必须在设置页明确选择允许上传的本地文件夹；未选择时不能开启音频上传。
- 新上传文件保留原文件名，直接放进服务器音乐库根目录；同名但内容不同才会附加短后缀。
- 原始文件始终保留。服务器以单个后台任务生成 128kbps AAC 缓存，网页同听优先读取缓存；缓存未完成时临时读取原文件。
- 缓存会复制可支持的内嵌元数据、封面和歌词，不显示在后台音乐库，也会在删除原曲时一并删除。
- 手动放入 `ALIVE_MUSIC_LIBRARY_HOST` 的音乐不会被改名或移动；服务重启后会在后台检查并补齐缓存。

`ALIVE_SERVER` 和 `ALIVE_MUSIC_DIR` 仅供仓库内旧版 Windows 上报脚本读取，Docker 服务本身不使用它们。本地播放器插件或客户端的服务器地址、密钥和允许上传文件夹在各自设置页配置。

## 后续更新

在项目目录依次执行以下两条命令：

```bash
git pull --ff-only
sudo docker compose up -d --build
```

第二条会重建镜像并重启服务，同时保留 `./data` 和 `ALIVE_MUSIC_LIBRARY_HOST` 中的持久化数据。若本次更新包含本地播放器插件改动，再重新导入最新插件包。

## 致谢

Alive 基于 [sleepy-project/sleepy](https://github.com/sleepy-project/sleepy) 重构而来，保留上游 MIT 许可，详见 [LICENSE](LICENSE)。

# Alive

个人在线状态页，提供设备、音乐上报和管理后台。

## 部署

```bash
cp .env.example .env
nano .env
sudo docker compose up -d --build
```

| 变量 | 说明 |
| --- | --- |
| `ALIVE_SECRET` | 必填。后台和上报客户端共用的密钥。 |
| `ALIVE_PAGE_NAME` | 必填。首页展示名称。 |
| `ALIVE_PORT` | 可选，对外端口，默认 `9010`。 |
| `ALIVE_MUSIC_LIBRARY_HOST` | 可选，宿主机音乐目录，默认 `./data/music-library`。容器内路径固定为 `/alive/music-library`。 |

反向代理将域名转发到 `127.0.0.1:ALIVE_PORT`；默认即 `127.0.0.1:9010`。

## 音乐

- 网易云在线流媒体：通过 `netease-api` 解析在线音源、封面和歌词；不下载文件，不写入本地音乐库。
- 本地播放器上报：上报歌词和元数据，可选上传当前音频。原文件保留，服务端后台生成 128kbps AAC 缓存供同听使用；缓存不显示在管理页，删除原曲时一并删除。手动放入音乐目录的文件不会被改名或移动。

本地播放器插件或客户端的服务器地址、密钥和允许上传文件夹在各自设置页配置。

## 更新

```bash
git pull --ff-only
sudo docker compose up -d --build
```

更新不会删除 `./data` 和音乐库数据；如包含插件更新，再重新导入插件包。

## 致谢

Alive 基于 [sleepy-project/sleepy](https://github.com/sleepy-project/sleepy) 重构，保留上游 MIT 许可，详见 [LICENSE](LICENSE)。

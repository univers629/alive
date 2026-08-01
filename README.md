# Alive

一个用 FastAPI 编写的个人在线状态页，提供公开状态页、设备与音乐上报 API、浏览器管理后台和 SQLite 持久化存储。

## Docker 部署

1. 复制环境变量示例：

   ```bash
   cp .env.example .env
   ```

2. 编辑 `.env`，填写初始值：

   ```bash
   nano .env
   ```

   必须设置的项目：

   | 变量 | 说明 |
   | --- | --- |
   | `ALIVE_SECRET` | 全局密钥，至少 6 位，后台和所有客户端共用，建议使用长随机值 |
   | `ALIVE_PAGE_NAME` | 首页展示的用户名 |

   可选项目：`ALIVE_PORT`（Docker 对外端口及服务监听端口，默认 `9010`）、`ALIVE_SERVER`（远程服务器地址）、`ALIVE_MUSIC_LIBRARY_HOST`（音乐目录）、`ALIVE_MUSIC_DIR`（Windows 音乐上报扫描目录）。

   例如改用 `18010`：

   ```env
   ALIVE_PORT=18010
   ```

   未设置 `ALIVE_PORT` 时，容器内外继续使用 `9010`，因此现有部署直接更新不会受影响。

3. 构建并启动：

   ```bash
   sudo docker compose up -d --build
   ```
3. 准备网页：

   配置反向代理与域名等

## 致谢

Alive 基于 [sleepy-project/sleepy](https://github.com/sleepy-project/sleepy) 重构而来，保留上游 MIT 许可，详见 [LICENSE](LICENSE)。

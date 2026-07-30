# 更新 Alive

先备份 `data/alive.db`，再更新代码：

```powershell
docker compose down
Copy-Item .\data\alive.db .\data\alive.backup.db
git pull --ff-only
docker compose up --build -d
docker compose logs --tail 100 alive
```

Alive 没有 v4 兼容层、旧数据迁移脚本或旧路由。升级 Alive 自身时，SQLite 数据库
和首页累计访问次数会通过 `data` 挂载继续保留。

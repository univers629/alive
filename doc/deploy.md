# Windows 与 Docker 部署

## 本地测试

在 PowerShell 中进入项目目录：

```powershell
Set-Location "C:\path\to\Alive"
Copy-Item .env.example .env
notepad .env
docker compose config
docker compose up --build
```

保持窗口运行，然后访问：

- <http://localhost:9010/>
- <http://localhost:9010/panel>
- <http://localhost:9010/docs>
- <http://localhost:9010/swagger>

另开 PowerShell 检查：

```powershell
docker compose ps
docker compose logs --tail 100 alive
curl.exe http://localhost:9010/api/status/query
```

停止服务：

```powershell
docker compose down
```

普通 `down` 不会删除 `./data/alive.db`。数据库位于 Windows 项目目录的
`data` 文件夹，可正常备份。

## 上报测试

```powershell
$secret = "填入 .env 中的 ALIVE_SECRET"
$headers = @{ Authorization = "Bearer $secret" }
$body = @{
  id = "windows-test"
  show_name = "Windows 测试机"
  using = $true
  status = "PowerShell"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:9010/api/device/set" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

刷新首页或后台即可看到设备。

## 生产部署提示

- 使用长度足够的随机密钥。
- 在 Caddy、Nginx 或其他反向代理后启用 HTTPS。
- 将 `ALIVE_MAIN_CORS_ORIGINS` 限制为实际站点来源。
- 定期备份 `data/alive.db`。
- 不要把 `.env`、数据库或证书提交到 Git。

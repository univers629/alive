# HTTPS

生产环境建议用 Caddy、Nginx 或云平台反向代理在 443 端口处理 HTTPS，再代理到
Alive 的 `9010` 端口。代理应传递 `X-Forwarded-Proto: https`，这样管理后台登录
Cookie 会自动设置 `Secure`。

也可以让 Uvicorn 直接读取证书，在 `data/config.yaml` 中配置：

```yaml
main:
  https: true
  ssl_cert: data/cert.pem
  ssl_key: data/key.pem
```

不要把私钥提交到 Git。证书和私钥文件应限制为仅服务账户可读。

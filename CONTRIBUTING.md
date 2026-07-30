# Contributing to Alive

提交改动前请运行：

```powershell
uv sync
uv run pytest
```

设计约束：

- 公开读取接口使用 GET。
- 任何改变状态或数据的接口必须使用 POST，并经过统一鉴权。
- 密钥不得放入 URL 或查询字符串。
- 不重新加入 v4 路由、Flask 兼容代码或旧数据迁移逻辑。
- 数据库结构或统计逻辑变化必须增加持久性测试。

请保持提交范围清晰，并在说明中列出 API 或配置的兼容性影响。

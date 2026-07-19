# 敏感词服务镜像迁移手册

迁移包包含应用镜像、Compose 配置、词库、环境变量模板、SHA-256 校验值和导入脚本。上传的 Word 只在请求过程中处理，不持久保存。管理员会话位于内存，迁移后需重新登录。Ollama 模型不包含在应用镜像中。

## 源机器导出

```powershell
powershell -ExecutionPolicy Bypass -File .\migration\export.ps1
```

将生成的整个 `releases\sensitive-filter-日期时间` 目录复制到目标机器。

## 目标机器部署

目标机器需安装并启动 Docker Desktop，使用 Linux 容器模式。

```powershell
powershell -ExecutionPolicy Bypass -File .\import.ps1
```

首次运行会校验并导入镜像、生成 `.env` 后停止。编辑 `.env`，设置新的强密码：

```text
ADMIN_PASSWORD=新的强密码
```

随后启动和验证：

```powershell
docker compose up -d
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
```

访问 `http://目标机器IP:8000/`。防火墙应只向可信内网开放 8000 端口。

## Ollama（可选）

Ollama 需在目标机单独安装和拉取模型，例如 `ollama pull qwen2.5:7b`。Compose 默认通过 `http://host.docker.internal:11434` 连接宿主机。规则检测与 Word 替换不依赖 Ollama。

## 备份、升级与回滚

持续备份 `data\words.json` 和 `.env`。升级前执行：

```powershell
docker image tag local-sensitive-filter:latest local-sensitive-filter:backup
Copy-Item .\data\words.json .\data\words.backup.json
```

升级：

```powershell
docker load --input .\local-sensitive-filter.tar
docker compose up -d --force-recreate
```

回滚：

```powershell
docker image tag local-sensitive-filter:backup local-sensitive-filter:latest
Copy-Item .\data\words.backup.json .\data\words.json
docker compose up -d --force-recreate
```

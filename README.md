# 本地文本敏感词查找与替换

规则检测完全在本机运行，采用 Aho-Corasick 多模式匹配；另提供可选的 Ollama 语义复核。默认词库仅含占位示例，请按业务要求维护 `data/words.json`。

## 启动 API

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn app:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/docs` 即可调用。主要接口：

- `POST /scan`：查找并返回词、分类、风险等级和字符位置
- `POST /replace`：替换命中内容
- `POST /scan-file`：扫描最大 10 MB 的 UTF-8 文本文件
- `POST /semantic-review`：规则扫描并调用本机 Ollama 复核
- `POST /scan-docx`：扫描 `.docx` 正文、表格、页眉和页脚
- `POST /replace-docx`：替换并下载新的 Word 文件

请求示例：

```json
{"text":"这里包含示例敏感词", "min_level":1, "replacement":"*"}
```

## 命令行

```powershell
python cli.py input.txt
python cli.py input.txt --replace "*" --output clean.txt
```

## 本地大模型（可选）

先安装并启动 Ollama，然后拉取模型：

```powershell
ollama pull qwen2.5:7b
```

默认连接 `http://127.0.0.1:11434`，可通过 `OLLAMA_BASE_URL` 修改地址。语义模型可能误判，因此接口把规则结果和模型建议分开返回，不直接按模型输出替换原文。

## 词库格式

```json
{"words":[{"word":"需要拦截的词", "category":"类别", "level":2}]}
```

`level` 取 1 到 3。修改词库后重启服务加载。生产部署时建议将服务仅绑定内网地址，并按组织政策配置正式词库。

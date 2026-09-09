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
- `POST /replace-docx-markdown`：替换 Word 中的敏感词，并按标题层级和表格结构导出 Markdown
- `POST /template-docx`：保留 Word 标题级别与内容、表格结构与表头、图片题注，删除正文及表格数据行内容
- `POST /format-docx-headings`：离线识别 Word 标题并将其字体统一为“黑体”，保留字号、字重及其他内容格式

Windows 上更新已有 Docker 部署时，在项目目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\update-deploy.ps1
```

脚本只允许快进拉取，随后重新构建并部署容器；现有 `.env` 和 `data\words.json` 不会被覆盖。

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

`level` 取 1 到 3。管理端可修改已有词条；保存后服务会自动重建匹配引擎，无需重启即可立即生效。生产部署时建议将服务仅绑定内网地址，并按组织政策配置正式词库。

## Office 文件支持

- Word：支持 `.docx` 正文、普通/合并/嵌套表格、页眉和页脚。
- Excel：支持 `.xlsx` 的所有工作表（包括隐藏工作表）中的文本单元格；公式、样式和合并区域保持不变。
- 默认上传上限为 100 MB，可通过 `MAX_UPLOAD_MB` 调整。
- 大文件会扫描和替换全部内容，但页面只展示前 200,000 个文本字符及前 2,000 条命中，避免浏览器卡顿。
- 旧版 `.doc` 和 `.xls` 需先另存为 `.docx` 和 `.xlsx`。

## 词库校验与反向恢复

- 敏感词不允许重复。
- 非空替换词必须唯一，且不能与任一敏感词相同，以保证映射可逆。
- 用户页面支持文本、DOCX 和 XLSX 的反向恢复，按 `replacement → word` 恢复。
- 反向恢复会处理文档中所有与替换词相同的文本；若替换词本来就是正常业务内容，也会被恢复，因此建议使用不易自然出现的替换词。

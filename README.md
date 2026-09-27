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

### Windows 离线批量替换（保留文件时间）

安装好上述 Python 依赖后，在 Windows 本机运行（Python 需包含 Tkinter）：

```powershell
python batch_gui.py
```

点击“批量导入文件”多选文件，选择本地词库和输出目录。
窗口现支持选择“正向替换”或“反向恢复”，点击“按所选模式处理并输出全部文件”执行。
正向按敏感词到替换词处理，输出 `_filtered` 文件；反向按词库的替换词到原词处理，输出 `_restored` 文件。
反向恢复只支持词库明确配置的映射，无法恢复使用通用 `*` 遮盖的原文；原本就存在的替换词也会被恢复。
存在重复替换词、无法确定唯一原词时拒绝恢复，需先修正词库。
窗口逐文件显示具体明细，例如 `“张三” → “某人员”（2 处）`，反向则显示 `“某人员” → “张三”（2 处）`。
明细汇总实际执行的不重叠变更，包含默认遮盖产生的实际输出，不把重叠命中重复计数。
支持混合导入 `.txt`、`.md`、`.csv`（UTF-8，保留 BOM 和换行）、`.docx`、`.xlsx`。
使用现有词库中的对应替换词，没有指定替换词的条目使用默认替换内容。
每个输入生成独立的 `_filtered` 文件；同名文件自动追加编号，不覆盖原文件或已有结果。
单个文件失败会显示原因，其他文件继续处理。

```powershell
python cli.py a.txt b.docx c.xlsx --replace "*" --output-dir .\output
python cli.py output\a_filtered.txt output\b_filtered.docx --restore --output-dir .\restored
```

输出文件通过 Windows 文件系统 API 保留输入的创建时间和最后修改时间，并逐个读回校验。
如果文件系统不支持精确保留或没有权限，报告失败并清理该失败输出，不把当前时间当作成功结果。
批量命令存在失败时退出码为 1。单文件 `--output` 同样保留时间，目标存在时拒绝覆盖。
此功能完全离线，不需要启动 API、Ollama 或任何网络服务；依赖须事先安装好。

浏览器上传只提供最后修改时间，不能读取原始创建时间，也不能设置下载文件的系统时间。
因此需要保留两种时间时请使用本地批量窗口或命令行；原网页下载不保证时间保留。
Linux/Docker 无法通过此入口完整设置 Windows 创建时间，明确报错；请在文件所在 Windows 主机运行。
这里保留的是文件系统时间，不是 Word/Excel 文档内部的属性日期。

### 文档属性和个人信息清理

本地窗口的正向替换、反向恢复、单独删除信息三个入口，对 DOCX/XLSX 均自动清理。
单独按钮无需词库，输出 `_cleaned` 文件；其他入口继续使用 `_filtered` / `_restored`。
清理核心、扩展、自定义文档属性（包括作者、公司、标题、内部日期等）、批注及人员记录、
自定义 XML、文档变量、缩略图、编辑人员标识、压缩条目附加元数据。
Word 修订会被接受：保留插入内容，删除已删除内容，移除修订历史及身份。
因此批注和修订历史不再保留；正文、公式、格式尽量保持当前最终内容。
文件系统创建/修改时间仍从输入复制并校验，文档内部日期属性则清除。
日志分别显示文字替换明细和信息清理项目，不再回显已清除的个人属性原值。
含嵌入附件或数字签名的文件报错，不输出未经完整检查的结果。

这不是任意文件的匿名化保证：正文姓名、图片内文字、图片 EXIF、超链接、隐藏工作表中的业务信息
不会由元数据清理自动识别或全部删除，需要词库及人工检查。TXT/MD/CSV 没有 Office 文档属性，
替换和恢复正常处理正文；单独信息清理只支持 DOCX/XLSX。上述功能属于本地窗口/CLI，原 Docker API 不变。

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

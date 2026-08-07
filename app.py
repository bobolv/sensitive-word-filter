from __future__ import annotations

import os
import secrets
import json
import threading
from urllib.parse import quote
from pathlib import Path

from fastapi import Cookie, File, HTTPException, Response, UploadFile
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sensitive_filter import SensitiveWordFilter
from sensitive_filter.semantic import review_with_ollama
from sensitive_filter.docx_handler import (
    create_writing_template,
    docx_to_markdown,
    replace_docx,
    scan_docx,
)
from sensitive_filter.xlsx_handler import replace_xlsx, scan_xlsx

BASE_DIR = Path(__file__).resolve().parent
WORDLIST = Path(os.getenv("SENSITIVE_WORDLIST", BASE_DIR / "data" / "words.json"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
def load_word_entries() -> list[dict]:
    data = json.loads(WORDLIST.read_text(encoding="utf-8"))
    entries = data.get("words", data) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError("词库必须是数组，或包含 words 数组的对象")
    return entries


def build_reverse_engine(entries: list[dict]) -> SensitiveWordFilter:
    reverse_entries = []
    for entry in entries:
        word = str(entry.get("word", "")).strip()
        replacement = str(entry.get("replacement", "")).strip()
        if not word or not replacement:
            continue
        reverse_entries.append({
            "word": replacement,
            "replacement": word,
            "category": entry.get("category", "未分类"),
            "level": entry.get("level", 1),
        })
    return SensitiveWordFilter(reverse_entries)


word_entries = load_word_entries()
engine = SensitiveWordFilter(word_entries)
reverse_engine = build_reverse_engine(word_entries)
app = FastAPI(title="本地文本敏感词服务", version="1.0.0", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
admin_sessions: set[str] = set()
wordlist_lock = threading.Lock()


@app.middleware("http")
async def disable_ui_cache(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path == "/admin" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1_000_000)
    min_level: int = Field(default=1, ge=1, le=3)


class ReplaceRequest(TextRequest):
    replacement: str = Field(default="*", min_length=1, max_length=20)


class SemanticRequest(TextRequest):
    model: str = "qwen2.5:7b"


class LoginRequest(BaseModel):
    password: str


class WordEntry(BaseModel):
    word: str = Field(min_length=1, max_length=200)
    category: str = Field(default="未分类", max_length=50)
    level: int = Field(default=1, ge=1, le=3)
    replacement: str = Field(default="", max_length=200)


class WordListRequest(BaseModel):
    words: list[WordEntry] = Field(max_length=100_000)


class WordUpdateRequest(BaseModel):
    original_word: str = Field(min_length=1, max_length=200)
    entry: WordEntry


def require_admin(admin_session: str | None) -> None:
    if not admin_session or admin_session not in admin_sessions:
        raise HTTPException(401, "请先登录管理端")


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/admin", include_in_schema=False)
def admin_page() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "admin.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "wordlist": str(WORDLIST)}


@app.post("/scan")
def scan(payload: TextRequest) -> dict:
    return engine.scan(payload.text, payload.min_level).to_dict()


@app.post("/replace")
def replace(payload: ReplaceRequest) -> dict:
    output, result = engine.replace(payload.text, payload.replacement, payload.min_level)
    return {**result.to_dict(), "text": output}


@app.post("/restore")
def restore(payload: TextRequest) -> dict:
    output, result = reverse_engine.replace(payload.text, "*", payload.min_level)
    return {**result.to_dict(), "text": output}


@app.post("/scan-file")
async def scan_file(file: UploadFile = File(...), min_level: int = 1) -> dict:
    if min_level not in (1, 2, 3):
        raise HTTPException(400, "min_level 只能是 1、2、3")
    content = await file.read(10_000_001)
    if len(content) > 10_000_000:
        raise HTTPException(413, "文件不能超过 10 MB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "文件必须是 UTF-8 编码的文本") from exc
    return {"filename": file.filename, **engine.scan(text, min_level).to_dict()}


async def read_upload(file: UploadFile, label: str) -> bytes:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"{label}文件不能超过 {MAX_UPLOAD_MB} MB")
    return content


def validate_office_file(file: UploadFile, content: bytes, extension: str, label: str) -> None:
    if not file.filename or not file.filename.lower().endswith(extension):
        raise HTTPException(400, f"目前仅支持 {extension} 格式的{label}文件")
    if not content.startswith(b"PK"):
        raise HTTPException(400, f"文件不是有效的 {extension.upper()} 文档")


@app.post("/scan-docx")
async def scan_word_file(file: UploadFile = File(...), min_level: int = 1) -> dict:
    if min_level not in (1, 2, 3):
        raise HTTPException(400, "min_level 只能是 1、2、3")
    content = await read_upload(file, "Word ")
    validate_office_file(file, content, ".docx", "Word ")
    try:
        return {"filename": file.filename, **scan_docx(content, engine, min_level)}
    except Exception as exc:
        raise HTTPException(400, f"无法读取 Word 文档：{exc}") from exc


@app.post("/replace-docx")
async def replace_word_file(
    file: UploadFile = File(...), replacement: str = "*", min_level: int = 1
) -> StreamingResponse:
    if min_level not in (1, 2, 3) or not replacement or len(replacement) > 20:
        raise HTTPException(400, "替换参数无效")
    content = await read_upload(file, "Word ")
    validate_office_file(file, content, ".docx", "Word ")
    try:
        output, _ = replace_docx(content, engine, replacement, min_level)
    except Exception as exc:
        raise HTTPException(400, f"无法处理 Word 文档：{exc}") from exc
    filename = f"{Path(file.filename).stem}_filtered.docx"
    encoded_filename = quote(filename)
    return StreamingResponse(
        iter([output]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=filtered.docx; filename*=UTF-8''{encoded_filename}"},
    )


@app.post("/restore-docx")
async def restore_word_file(file: UploadFile = File(...), min_level: int = 1) -> StreamingResponse:
    if min_level not in (1, 2, 3):
        raise HTTPException(400, "min_level 只能是 1、2、3")
    content = await read_upload(file, "Word ")
    validate_office_file(file, content, ".docx", "Word ")
    try:
        output, _ = replace_docx(content, reverse_engine, "*", min_level)
    except Exception as exc:
        raise HTTPException(400, f"无法恢复 Word 文档：{exc}") from exc
    filename = f"{Path(file.filename).stem}_restored.docx"
    encoded_filename = quote(filename)
    return StreamingResponse(
        iter([output]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=restored.docx; filename*=UTF-8''{encoded_filename}"},
    )


@app.post("/replace-docx-markdown")
async def replace_word_as_markdown(
    file: UploadFile = File(...), replacement: str = "*", min_level: int = 1
) -> StreamingResponse:
    if min_level not in (1, 2, 3) or not replacement or len(replacement) > 20:
        raise HTTPException(400, "替换参数无效")
    content = await read_upload(file, "Word ")
    validate_office_file(file, content, ".docx", "Word ")
    try:
        output, _ = docx_to_markdown(content, engine, replacement, min_level)
    except Exception as exc:
        raise HTTPException(400, f"无法将 Word 文档转换为 Markdown：{exc}") from exc
    filename = f"{Path(file.filename).stem}_filtered.md"
    encoded_filename = quote(filename)
    return StreamingResponse(
        iter([output]),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=filtered.md; filename*=UTF-8''{encoded_filename}"},
    )


@app.post("/template-docx")
async def make_word_template(file: UploadFile = File(...)) -> StreamingResponse:
    content = await read_upload(file, "Word ")
    validate_office_file(file, content, ".docx", "Word ")
    try:
        output, _ = create_writing_template(content)
    except Exception as exc:
        raise HTTPException(400, f"无法生成 Word 编写模板：{exc}") from exc
    filename = f"{Path(file.filename).stem}_template.docx"
    encoded_filename = quote(filename)
    return StreamingResponse(
        iter([output]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=template.docx; filename*=UTF-8''{encoded_filename}"},
    )


@app.post("/scan-xlsx")
async def scan_excel_file(file: UploadFile = File(...), min_level: int = 1) -> dict:
    if min_level not in (1, 2, 3):
        raise HTTPException(400, "min_level 只能是 1、2、3")
    content = await read_upload(file, "Excel ")
    validate_office_file(file, content, ".xlsx", "Excel ")
    try:
        return {"filename": file.filename, **scan_xlsx(content, engine, min_level)}
    except Exception as exc:
        raise HTTPException(400, f"无法读取 Excel 工作簿：{exc}") from exc


@app.post("/replace-xlsx")
async def replace_excel_file(
    file: UploadFile = File(...), replacement: str = "*", min_level: int = 1
) -> StreamingResponse:
    if min_level not in (1, 2, 3) or not replacement or len(replacement) > 20:
        raise HTTPException(400, "替换参数无效")
    content = await read_upload(file, "Excel ")
    validate_office_file(file, content, ".xlsx", "Excel ")
    try:
        output, _ = replace_xlsx(content, engine, replacement, min_level)
    except Exception as exc:
        raise HTTPException(400, f"无法处理 Excel 工作簿：{exc}") from exc
    filename = f"{Path(file.filename).stem}_filtered.xlsx"
    encoded_filename = quote(filename)
    return StreamingResponse(
        iter([output]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=filtered.xlsx; filename*=UTF-8''{encoded_filename}"},
    )


@app.post("/restore-xlsx")
async def restore_excel_file(file: UploadFile = File(...), min_level: int = 1) -> StreamingResponse:
    if min_level not in (1, 2, 3):
        raise HTTPException(400, "min_level 只能是 1、2、3")
    content = await read_upload(file, "Excel ")
    validate_office_file(file, content, ".xlsx", "Excel ")
    try:
        output, _ = replace_xlsx(content, reverse_engine, "*", min_level)
    except Exception as exc:
        raise HTTPException(400, f"无法恢复 Excel 工作簿：{exc}") from exc
    filename = f"{Path(file.filename).stem}_restored.xlsx"
    encoded_filename = quote(filename)
    return StreamingResponse(
        iter([output]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=restored.xlsx; filename*=UTF-8''{encoded_filename}"},
    )


@app.post("/semantic-review")
async def semantic_review(payload: SemanticRequest) -> dict:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    try:
        semantic = await review_with_ollama(payload.text, payload.model, base_url)
    except Exception as exc:
        raise HTTPException(503, f"本地模型服务不可用：{exc}") from exc
    rules = engine.scan(payload.text, payload.min_level).to_dict()
    return {"rules": rules, "semantic": semantic}


@app.post("/admin/login", include_in_schema=False)
def admin_login(payload: LoginRequest, response: Response) -> dict:
    expected = os.getenv("ADMIN_PASSWORD")
    if not expected or not secrets.compare_digest(payload.password, expected):
        raise HTTPException(401, "密码错误")
    token = secrets.token_urlsafe(32)
    admin_sessions.add(token)
    response.set_cookie("admin_session", token, httponly=True, samesite="strict", max_age=28800)
    return {"ok": True}


@app.post("/admin/logout", include_in_schema=False)
def admin_logout(response: Response, admin_session: str | None = Cookie(default=None)) -> dict:
    if admin_session:
        admin_sessions.discard(admin_session)
    response.delete_cookie("admin_session")
    return {"ok": True}


@app.get("/admin/words", include_in_schema=False)
def get_words(admin_session: str | None = Cookie(default=None)) -> dict:
    require_admin(admin_session)
    return json.loads(WORDLIST.read_text(encoding="utf-8"))


def validate_word_entries(entries: list[dict]) -> None:
    seen_words: set[str] = set()
    seen_replacements: set[str] = set()
    normalized_words = {str(item.get("word", "")).strip().casefold() for item in entries}

    for entry in entries:
        word = str(entry.get("word", "")).strip()
        replacement = str(entry.get("replacement", "")).strip()
        normalized_word = word.casefold()
        normalized_replacement = replacement.casefold()
        if normalized_word in seen_words:
            raise HTTPException(409, "敏感词已添加")
        seen_words.add(normalized_word)
        if not replacement:
            continue
        if normalized_replacement in seen_replacements:
            raise HTTPException(409, "替换词存在重复情况，请修改")
        if normalized_replacement in normalized_words:
            raise HTTPException(409, "替换词与敏感词存在重复情况，请修改")
        seen_replacements.add(normalized_replacement)


def activate_word_entries(entries: list[dict]) -> None:
    """Validate, persist atomically, and switch the live matching engines."""
    global engine, reverse_engine, word_entries
    validate_word_entries(entries)
    new_engine = SensitiveWordFilter(entries)
    new_reverse_engine = build_reverse_engine(entries)
    data = {"words": entries}
    temporary_wordlist = WORDLIST.with_suffix(f"{WORDLIST.suffix}.tmp")
    temporary_wordlist.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    try:
        temporary_wordlist.replace(WORDLIST)
    except OSError:
        # Docker 单文件挂载不能被 rename/replace 覆盖，改为原位写入。
        WORDLIST.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary_wordlist.unlink(missing_ok=True)
    engine = new_engine
    reverse_engine = new_reverse_engine
    word_entries = entries


@app.put("/admin/words", include_in_schema=False)
def save_words(payload: WordListRequest, admin_session: str | None = Cookie(default=None)) -> dict:
    require_admin(admin_session)
    entries = [item.model_dump() for item in payload.words]
    with wordlist_lock:
        activate_word_entries(entries)
    return {"ok": True, "count": len(entries)}


@app.patch("/admin/words", include_in_schema=False)
def update_word(payload: WordUpdateRequest, admin_session: str | None = Cookie(default=None)) -> dict:
    require_admin(admin_session)
    original_word = payload.original_word.strip().casefold()
    with wordlist_lock:
        entries = load_word_entries()
        indexes = [
            index for index, item in enumerate(entries)
            if str(item.get("word", "")).strip().casefold() == original_word
        ]
        if not indexes:
            raise HTTPException(404, "要修改的词条不存在，请刷新后重试")
        entries[indexes[0]] = payload.entry.model_dump()
        activate_word_entries(entries)
    return {"ok": True, "count": len(entries), "word": payload.entry.word}

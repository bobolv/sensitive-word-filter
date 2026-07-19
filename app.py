from __future__ import annotations

import os
import secrets
from urllib.parse import quote
from pathlib import Path

from fastapi import Cookie, File, HTTPException, Response, UploadFile
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sensitive_filter import SensitiveWordFilter
from sensitive_filter.semantic import review_with_ollama
from sensitive_filter.docx_handler import replace_docx, scan_docx

BASE_DIR = Path(__file__).resolve().parent
WORDLIST = Path(os.getenv("SENSITIVE_WORDLIST", BASE_DIR / "data" / "words.json"))
engine = SensitiveWordFilter.from_json(WORDLIST)
app = FastAPI(title="本地文本敏感词服务", version="1.0.0", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
admin_sessions: set[str] = set()


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


def validate_docx(file: UploadFile, content: bytes) -> None:
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "目前仅支持 .docx，请将旧版 .doc 另存为 .docx")
    if len(content) > 20_000_000:
        raise HTTPException(413, "Word 文件不能超过 20 MB")
    if not content.startswith(b"PK"):
        raise HTTPException(400, "文件不是有效的 DOCX 文档")


@app.post("/scan-docx")
async def scan_word_file(file: UploadFile = File(...), min_level: int = 1) -> dict:
    if min_level not in (1, 2, 3):
        raise HTTPException(400, "min_level 只能是 1、2、3")
    content = await file.read(20_000_001)
    validate_docx(file, content)
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
    content = await file.read(20_000_001)
    validate_docx(file, content)
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
    import json
    return json.loads(WORDLIST.read_text(encoding="utf-8"))


@app.put("/admin/words", include_in_schema=False)
def save_words(payload: WordListRequest, admin_session: str | None = Cookie(default=None)) -> dict:
    require_admin(admin_session)
    import json
    global engine
    data = {"words": [item.model_dump() for item in payload.words]}
    WORDLIST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    engine = SensitiveWordFilter(data["words"])
    return {"ok": True, "count": len(data["words"])}

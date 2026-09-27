"""Offline filesystem processing. Windows preserves creation/write times exactly."""
from __future__ import annotations

import ctypes
import os
import json
from collections import Counter
from pathlib import Path

from . import SensitiveWordFilter

SUPPORTED = {".txt", ".md", ".csv", ".docx", ".xlsx"}


def load_batch_engine(path: Path, mode: str = "replace") -> SensitiveWordFilter:
    if mode not in ("replace", "restore"):
        raise ValueError("无效处理模式")
    if mode == "replace":
        return SensitiveWordFilter.from_json(path)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = data.get("words", data) if isinstance(data, dict) else data
    reverse, seen = [], set()
    for entry in entries:
        word = str(entry.get("word", "")).strip()
        substitute = str(entry.get("replacement", "")).strip()
        if not word or not substitute:
            continue
        if substitute.casefold() in seen:
            raise ValueError(f"替换词“{substitute}”对应多个词条，无法唯一恢复，请修改词库")
        seen.add(substitute.casefold())
        reverse.append({**entry, "word": substitute, "replacement": word})
    if not reverse:
        raise ValueError("词库没有可反向恢复的替换词；通用星号遮盖无法恢复")
    return SensitiveWordFilter(reverse)


class _RecordingEngine(SensitiveWordFilter):
    """Record actual nonoverlapping edits at the handlers' replacement boundary."""
    def __init__(self, engine):
        self.engine = engine
        self.changes = Counter()

    def scan(self, text, min_level=1):
        return self.engine.scan(text, min_level)

    def replacement_ranges(self, text, replacement="*", min_level=1):
        ranges = self.engine.replacement_ranges(text, replacement, min_level)
        for start, end, value in ranges:
            if text[start:end] != value:
                self.changes[(text[start:end], value)] += 1
        return ranges


def copy_times(source: Path, destination: Path, snapshot: os.stat_result) -> None:
    if os.name != "nt":
        raise OSError("完整保留创建时间需要在 Windows 本机运行（不支持 Linux/Docker）")
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    get = kernel.GetFileTime
    set_time = kernel.SetFileTime
    for function in (get, set_time):
        function.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 3
        function.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL

    def open_handle(path, access):
        handle = create(str(path.resolve()), access, 7, None, 3, 0, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    creation, access, modified = (wintypes.FILETIME() for _ in range(3))
    handle = open_handle(source, 0x80)  # FILE_READ_ATTRIBUTES
    try:
        if not get(handle, ctypes.byref(creation), ctypes.byref(access), ctypes.byref(modified)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        close(handle)
    if source.stat().st_mtime_ns != snapshot.st_mtime_ns:
        raise OSError("源文件处理期间发生修改，请重试")
    handle = open_handle(destination, 0x100)  # FILE_WRITE_ATTRIBUTES
    try:
        if not set_time(handle, ctypes.byref(creation), ctypes.byref(access), ctypes.byref(modified)):
            raise ctypes.WinError(ctypes.get_last_error())
        actual = [wintypes.FILETIME() for _ in range(3)]
    finally:
        close(handle)
    handle = open_handle(destination, 0x80)
    try:
        if not get(handle, *(ctypes.byref(value) for value in actual)):
            raise ctypes.WinError(ctypes.get_last_error())
        if bytes(actual[0]) != bytes(creation) or bytes(actual[2]) != bytes(modified):
            raise OSError("输出文件系统无法精确保留创建时间和修改时间")
    finally:
        close(handle)


def replace_file(source: Path, destination: Path, engine: SensitiveWordFilter | None,
                 replacement: str = "*", min_level: int = 1,
                 clear_authors: bool = False) -> dict:
    source, destination = Path(source), Path(destination)
    if os.name != "nt":
        raise OSError("完整保留创建时间需要 Windows 本机运行")
    if source.suffix.lower() not in SUPPORTED:
        raise ValueError("不支持的文件类型：" + source.suffix)
    if not replacement or len(replacement) > 20 or min_level not in (1, 2, 3):
        raise ValueError("替换参数无效")
    snapshot = source.stat()
    content = source.read_bytes()
    pre_privacy = {"count": 0, "changes": []}
    if not clear_authors and source.suffix.lower() in (".docx", ".xlsx"):
        from .metadata import clear_author_properties
        content, pre_privacy = clear_author_properties(content, source.suffix)
    engine = _RecordingEngine(engine) if engine is not None else None
    if clear_authors:
        from .metadata import clear_author_properties
        output, result = clear_author_properties(content, source.suffix)
    elif engine is None:
        raise ValueError("替换操作需要词库")
    elif source.suffix.lower() == ".docx":
        from .docx_handler import replace_docx
        output, result = replace_docx(content, engine, replacement, min_level)
    elif source.suffix.lower() == ".xlsx":
        from .xlsx_handler import replace_xlsx
        output, result = replace_xlsx(content, engine, replacement, min_level)
    else:
        encoding = "utf-8-sig" if content.startswith(b"\xef\xbb\xbf") else "utf-8"
        output_text, scan = engine.replace(content.decode(encoding), replacement, min_level)
        output, result = output_text.encode(encoding), scan.to_dict()
    privacy = result if clear_authors else {"count": 0, "changes": []}
    if not clear_authors and source.suffix.lower() in (".docx", ".xlsx"):
        from .metadata import clear_author_properties
        output, privacy = clear_author_properties(output, source.suffix)
        privacy["count"] += pre_privacy["count"]
        privacy["changes"] = pre_privacy["changes"] + privacy["changes"]
    result["privacy"] = {"count": privacy["count"], "changes": privacy["changes"]}
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects originals and previously generated files.
    with destination.open("xb") as stream:
        try:
            stream.write(output)
        except BaseException:
            stream.close()
            destination.unlink()
            raise
    try:
        copy_times(source, destination, snapshot)
    except BaseException:
        destination.unlink()
        raise
    if not clear_authors:
        result["changes"] = [{"before": before, "after": after, "count": count}
                             for (before, after), count in engine.changes.items()]
        result["count"] = sum(engine.changes.values())
    return result


def replace_batch(sources, output_dir: Path, engine: SensitiveWordFilter | None,
                  replacement: str = "*", min_level: int = 1, progress=None,
                  mode: str = "replace") -> list[dict]:
    if mode not in ("replace", "restore", "clear_authors"):
        raise ValueError("无效处理模式")
    suffix = {"restore": "restored", "replace": "filtered", "clear_authors": "cleaned"}[mode]
    results = []
    for source in map(Path, sources):
        destination = Path(output_dir) / f"{source.stem}_{suffix}{source.suffix}"
        index = 2
        while destination.exists():
            destination = Path(output_dir) / f"{source.stem}_{suffix}_{index}{source.suffix}"
            index += 1
        try:
            report = replace_file(source, destination, engine, replacement, min_level,
                                  clear_authors=mode == "clear_authors")
            item = {"source": str(source), "output": str(destination), "ok": True,
                    "count": report["count"], "changes": report["changes"], "mode": mode,
                    "privacy": report["privacy"]}
        except Exception as exc:
            item = {"source": str(source), "ok": False, "error": str(exc)}
        results.append(item)
        if progress:
            progress(item)
    return results

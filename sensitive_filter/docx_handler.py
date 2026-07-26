from __future__ import annotations

from io import BytesIO

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from .engine import SensitiveWordFilter


def _part_paragraphs(element, owner, seen: set[object]):
    """遍历部件内所有段落，包括表格、嵌套表格和内容控件。"""
    for paragraph_element in element.iter(qn("w:p")):
        if paragraph_element in seen:
            continue
        seen.add(paragraph_element)
        yield Paragraph(paragraph_element, owner)


def iter_document_paragraphs(document):
    seen: set[object] = set()
    yield from _part_paragraphs(document.element.body, document, seen)

    seen_parts: set[str] = set()
    for section in document.sections:
        for part in (section.header, section.footer):
            key = str(part.part.partname)
            if key in seen_parts:
                continue
            seen_parts.add(key)
            yield from _part_paragraphs(part._element, part, seen)


def document_text(document) -> str:
    return "\n".join(paragraph.text for paragraph in iter_document_paragraphs(document) if paragraph.text)


def _limited_result(result, match_limit: int) -> dict:
    return {
        "sensitive": result.sensitive,
        "count": len(result.matches),
        "matches": [match.to_dict() for match in result.matches[:match_limit]],
        "matches_truncated": len(result.matches) > match_limit,
    }


def scan_docx(
    content: bytes,
    engine: SensitiveWordFilter,
    min_level: int = 1,
    preview_limit: int = 200_000,
    match_limit: int = 2_000,
) -> dict:
    text = document_text(Document(BytesIO(content)))
    result = engine.scan(text, min_level)
    preview = text[:preview_limit]
    return {
        "text": preview,
        "text_preview": preview,
        "text_length": len(text),
        "text_truncated": len(text) > preview_limit,
        **_limited_result(result, match_limit),
    }


def _replace_range(paragraph, start: int, end: int, replacement: str) -> None:
    positions, cursor = [], 0
    for run in paragraph.runs:
        positions.append((cursor, cursor + len(run.text)))
        cursor += len(run.text)

    touched = []
    for index, (run_start, run_end) in enumerate(positions):
        local_start = max(start, run_start) - run_start
        local_end = min(end, run_end) - run_start
        if local_start < local_end:
            touched.append((index, local_start, local_end))
    if not touched:
        return

    first = touched[0][0]
    for index, local_start, local_end in reversed(touched):
        run = paragraph.runs[index]
        inserted = replacement if index == first else ""
        run.text = run.text[:local_start] + inserted + run.text[local_end:]


def replace_docx(
    content: bytes,
    engine: SensitiveWordFilter,
    replacement: str = "*",
    min_level: int = 1,
):
    document = Document(BytesIO(content))
    total_matches = 0
    changed_paragraphs = 0

    # 按段处理，避免大文档再次拼接一份完整文本用于替换。
    for paragraph in iter_document_paragraphs(document):
        ranges = engine.replacement_ranges(paragraph.text, replacement, min_level)
        total_matches += len(ranges)
        if ranges:
            changed_paragraphs += 1
        for start, end, value in reversed(ranges):
            _replace_range(paragraph, start, end, value)

    output = BytesIO()
    document.save(output)
    return output.getvalue(), {
        "sensitive": total_matches > 0,
        "count": total_matches,
        "changed_paragraphs": changed_paragraphs,
    }

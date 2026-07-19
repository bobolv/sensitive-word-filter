from __future__ import annotations

from io import BytesIO

from docx import Document

from .engine import SensitiveWordFilter


def _table_paragraphs(table):
    seen = set()
    for row in table.rows:
        for cell in row.cells:
            key = id(cell._tc)
            if key in seen:
                continue
            seen.add(key)
            yield from _container_paragraphs(cell)


def _container_paragraphs(container):
    yield from container.paragraphs
    for table in container.tables:
        yield from _table_paragraphs(table)


def iter_document_paragraphs(document):
    yield from _container_paragraphs(document)
    seen_parts = set()
    for section in document.sections:
        for part in (section.header, section.footer):
            key = str(part.part.partname)
            if key not in seen_parts:
                seen_parts.add(key)
                yield from _container_paragraphs(part)


def document_text(document) -> str:
    return "\n".join(p.text for p in iter_document_paragraphs(document) if p.text)


def scan_docx(content: bytes, engine: SensitiveWordFilter, min_level: int = 1) -> dict:
    text = document_text(Document(BytesIO(content)))
    return {"text": text, **engine.scan(text, min_level).to_dict()}


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


def replace_docx(content: bytes, engine: SensitiveWordFilter, replacement: str = "*", min_level: int = 1):
    document = Document(BytesIO(content))
    result = engine.scan(document_text(document), min_level)
    changed = 0
    for paragraph in iter_document_paragraphs(document):
        ranges = engine.replacement_ranges(paragraph.text, replacement, min_level)
        if ranges:
            changed += 1
        for start, end, value in reversed(ranges):
            _replace_range(paragraph, start, end, value)
    output = BytesIO()
    document.save(output)
    return output.getvalue(), {**result.to_dict(), "changed_paragraphs": changed}

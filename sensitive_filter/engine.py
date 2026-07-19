from __future__ import annotations

import json
from pathlib import Path

from .models import Match, ScanResult


class _Node:
    __slots__ = ("children", "fail", "outputs")

    def __init__(self) -> None:
        self.children: dict[str, _Node] = {}
        self.fail: _Node | None = None
        self.outputs: list[tuple[str, str, int]] = []


class SensitiveWordFilter:
    """基于 Aho-Corasick 的本地多模式敏感词检测器。"""

    def __init__(self, entries: list[dict], ignore_case: bool = True) -> None:
        self.ignore_case = ignore_case
        self.root = _Node()
        self.root.fail = self.root
        self.replacements: dict[str, str] = {}
        self._build(entries)

    @classmethod
    def from_json(cls, path: str | Path, ignore_case: bool = True) -> "SensitiveWordFilter":
        with Path(path).open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        entries = data.get("words", data) if isinstance(data, dict) else data
        if not isinstance(entries, list):
            raise ValueError("词库必须是数组，或包含 words 数组的对象")
        return cls(entries, ignore_case=ignore_case)

    def _norm(self, value: str) -> str:
        return value.casefold() if self.ignore_case else value

    def _build(self, entries: list[dict]) -> None:
        for entry in entries:
            word = str(entry.get("word", "")).strip()
            if not word:
                continue
            custom_replacement = str(entry.get("replacement", "")).strip()
            if custom_replacement:
                self.replacements[self._norm(word)] = custom_replacement
            node = self.root
            for char in self._norm(word):
                node = node.children.setdefault(char, _Node())
            node.outputs.append((word, str(entry.get("category", "未分类")), int(entry.get("level", 1))))

        queue = list(self.root.children.values())
        for node in queue:
            node.fail = self.root
        index = 0
        while index < len(queue):
            current = queue[index]
            index += 1
            for char, child in current.children.items():
                fallback = current.fail
                while fallback is not self.root and char not in fallback.children:
                    fallback = fallback.fail
                child.fail = fallback.children.get(char, self.root)
                child.outputs.extend(child.fail.outputs)
                queue.append(child)

    def scan(self, text: str, min_level: int = 1) -> ScanResult:
        node = self.root
        matches: list[Match] = []
        normalized = self._norm(text)
        for pos, char in enumerate(normalized):
            while node is not self.root and char not in node.children:
                node = node.fail
            node = node.children.get(char, self.root)
            for word, category, level in node.outputs:
                if level < min_level:
                    continue
                start = pos - len(self._norm(word)) + 1
                matches.append(Match(word, category, level, start, pos + 1, text[start : pos + 1]))
        matches.sort(key=lambda item: (item.start, -(item.end - item.start), -item.level))
        return ScanResult(text, matches)

    def replacement_ranges(self, text: str, replacement: str = "*", min_level: int = 1):
        """返回无重叠替换区间；同起点优先最长词条。"""
        selected = []
        cursor = -1
        for match in self.scan(text, min_level).matches:
            if match.start < cursor:
                continue
            custom = self.replacements.get(self._norm(match.word))
            value = custom or (replacement * (match.end - match.start) if len(replacement) == 1 else replacement)
            selected.append((match.start, match.end, value))
            cursor = match.end
        return selected

    def replace(self, text: str, replacement: str = "*", min_level: int = 1) -> tuple[str, ScanResult]:
        result = self.scan(text, min_level=min_level)
        if not result.matches:
            return text, result
        output = text
        for start, end, value in reversed(self.replacement_ranges(text, replacement, min_level)):
            output = output[:start] + value + output[end:]
        return output, result

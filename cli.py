from __future__ import annotations

import argparse
import json
from pathlib import Path

from sensitive_filter import SensitiveWordFilter


def main() -> None:
    parser = argparse.ArgumentParser(description="本地敏感词扫描与替换")
    parser.add_argument("file", type=Path, help="UTF-8 文本文件")
    parser.add_argument("--words", type=Path, default=Path("data/words.json"))
    parser.add_argument("--replace", metavar="TEXT", help="执行替换；例如 '*' 或 '[已过滤]'")
    parser.add_argument("--output", type=Path, help="替换后的输出文件；不传则仅打印")
    parser.add_argument("--min-level", type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args()

    text = args.file.read_text(encoding="utf-8-sig")
    engine = SensitiveWordFilter.from_json(args.words)
    if args.replace is None:
        print(json.dumps(engine.scan(text, args.min_level).to_dict(), ensure_ascii=False, indent=2))
        return
    output, result = engine.replace(text, args.replace, args.min_level)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


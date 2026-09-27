from __future__ import annotations

import argparse
import json
from pathlib import Path

def main() -> None:
    parser = argparse.ArgumentParser(description="本地敏感词扫描与替换")
    parser.add_argument("file", type=Path, nargs="+", help="一个或多个输入文件")
    parser.add_argument("--output-dir", type=Path, help="批量输出目录（Windows，保留创建/修改时间）")
    parser.add_argument("--words", type=Path, default=Path("data/words.json"))
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--replace", metavar="TEXT", help="执行替换；例如 '*' 或 '[已过滤]'")
    operation.add_argument("--restore", action="store_true", help="按词库反向恢复")
    parser.add_argument("--output", type=Path, help="替换后的输出文件；不传则仅打印")
    parser.add_argument("--min-level", type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args()

    from sensitive_filter.batch import load_batch_engine
    mode = "restore" if args.restore else "replace"
    engine = load_batch_engine(args.words, mode)
    if args.restore:
        args.replace = "*"
    if args.output_dir:
        if args.replace is None or args.output:
            parser.error("--output-dir 必须配合 --replace 或 --restore，且不能同时指定 --output")
        from sensitive_filter.batch import replace_batch
        results = replace_batch(args.file, args.output_dir, engine, args.replace, args.min_level, mode=mode)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        raise SystemExit(1 if any(not item["ok"] for item in results) else 0)
    if len(args.file) != 1:
        parser.error("多个文件请指定 --replace 和 --output-dir")
    source = args.file[0]
    if args.output and args.replace is not None:
        from sensitive_filter.batch import replace_file
        result = replace_file(source, args.output, engine, args.replace, args.min_level)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    text = source.read_text(encoding="utf-8-sig")
    if args.replace is None:
        print(json.dumps(engine.scan(text, args.min_level).to_dict(), ensure_ascii=False, indent=2))
        return
    output, result = engine.replace(text, args.replace, args.min_level)
    print(output)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

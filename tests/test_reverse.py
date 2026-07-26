from fastapi import HTTPException

from app import build_reverse_engine, validate_word_entries
from sensitive_filter import SensitiveWordFilter


entries = [
    {"word": "张三", "replacement": "某人员", "category": "姓名", "level": 1},
    {"word": "机密", "replacement": "JM", "category": "保密", "level": 3},
]

validate_word_entries(entries)
forward = SensitiveWordFilter(entries)
reverse = build_reverse_engine(entries)
filtered, _ = forward.replace("张三查看机密")
assert filtered == "某人员查看JM"
restored, result = reverse.replace(filtered)
assert restored == "张三查看机密"
assert len(result.matches) == 2

try:
    validate_word_entries(entries + [
        {"word": "张三", "replacement": "其他", "category": "测试", "level": 1},
    ])
    raise AssertionError("duplicate sensitive word was accepted")
except HTTPException as exc:
    assert exc.status_code == 409
    assert exc.detail == "敏感词已添加"

try:
    validate_word_entries(entries + [
        {"word": "秘密", "replacement": "JM", "category": "测试", "level": 1},
    ])
    raise AssertionError("duplicate replacement was accepted")
except HTTPException as exc:
    assert exc.status_code == 409
    assert exc.detail == "替换词存在重复情况，请修改"

try:
    validate_word_entries([
        {"word": "张三", "replacement": "机密", "category": "测试", "level": 1},
        {"word": "机密", "replacement": "JM", "category": "测试", "level": 1},
    ])
    raise AssertionError("replacement/sensitive collision was accepted")
except HTTPException as exc:
    assert exc.status_code == 409
    assert exc.detail == "替换词与敏感词存在重复情况，请修改"

print("dictionary validation and reverse mapping passed")

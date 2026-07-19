from sensitive_filter import SensitiveWordFilter


def make_filter():
    return SensitiveWordFilter([
        {"word": "敏感词", "category": "测试", "level": 2},
        {"word": "bad", "category": "英文", "level": 1},
        {"word": "敏感", "category": "短词", "level": 1},
    ])


def test_scan_positions_and_case():
    result = make_filter().scan("这里有敏感词和BAD")
    assert result.sensitive
    assert any(m.word == "敏感词" and m.matched_text == "敏感词" for m in result.matches)
    assert any(m.word == "bad" and m.matched_text == "BAD" for m in result.matches)


def test_min_level():
    result = make_filter().scan("敏感词 bad", min_level=2)
    assert [m.word for m in result.matches] == ["敏感词"]


def test_overlapping_replace():
    output, result = make_filter().replace("发现敏感词", "*")
    assert output == "发现***"
    assert len(result.matches) == 2


def test_custom_replacement_has_priority():
    engine = SensitiveWordFilter([
        {"word": "张三", "category": "姓名", "level": 1, "replacement": "某人员"},
        {"word": "机密", "category": "保密", "level": 1},
    ])
    output, _ = engine.replace("张三查看机密", "[隐藏]")
    assert output == "某人员查看[隐藏]"

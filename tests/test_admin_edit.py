import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

import app as application


original_wordlist = application.WORDLIST
original_engine = application.engine
original_reverse_engine = application.reverse_engine
original_entries = application.word_entries

try:
    with TemporaryDirectory() as directory:
        wordlist = Path(directory) / "words.json"
        wordlist.write_text(
            json.dumps({"words": [{"word": "旧词", "category": "测试", "level": 1, "replacement": "旧替换"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        application.WORDLIST = wordlist
        application.activate_word_entries(application.load_word_entries())
        os.environ["ADMIN_PASSWORD"] = "test-password"

        with TestClient(application.app) as client:
            assert client.post("/admin/login", json={"password": "test-password"}).status_code == 200
            response = client.patch(
                "/admin/words",
                json={
                    "original_word": "旧词",
                    "entry": {"word": "新词", "category": "新分类", "level": 2, "replacement": "新替换"},
                },
            )
            assert response.status_code == 200, response.text
            assert client.post("/scan", json={"text": "旧词和新词", "min_level": 1}).json()["matches"] == [
                {"word": "新词", "category": "新分类", "level": 2, "start": 3, "end": 5, "matched_text": "新词"}
            ]
            saved = json.loads(wordlist.read_text(encoding="utf-8"))
            assert saved["words"][0]["word"] == "新词"
finally:
    application.WORDLIST = original_wordlist
    application.engine = original_engine
    application.reverse_engine = original_reverse_engine
    application.word_entries = original_entries
    os.environ.pop("ADMIN_PASSWORD", None)

print("admin existing-word edit and immediate activation passed")

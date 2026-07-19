from __future__ import annotations

import json

import httpx


async def review_with_ollama(text: str, model: str, base_url: str, timeout: float = 60) -> dict:
    """调用本机 Ollama；只返回结构化风险建议，不自动覆盖规则结果。"""
    prompt = (
        "你是中文内容安全审核器。判断文本是否包含违法、暴力、仇恨、色情、诈骗或隐私风险。"
        "仅输出 JSON，不要 Markdown，格式："
        '{"sensitive":true,"risk_level":1,"categories":[],"reason":""}。'
        "risk_level 为 0-3。待审核文本：\n" + text
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
        )
        response.raise_for_status()
        raw = response.json().get("response", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"sensitive": False, "risk_level": 0, "categories": [], "reason": raw, "parse_error": True}


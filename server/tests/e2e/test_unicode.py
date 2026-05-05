"""CJK, emoji, code blocks, and triple-backtick markdown survive end-to-end."""
import httpx
import pytest


SAMPLES = {
    "chinese": "为什么 Postgres 全文搜索对中文不友好？",
    "japanese": "テストの意味",
    "emoji": "🚀💥 fire on prod 🔥",
    "codeblock": "```python\ndef ok():\n    return '中文 + emoji 🎉'\n```",
    "tabs_newlines": "line1\n\tindented\n\nblank-above",
    "json_in_text": '{"nested": "value", "list": [1, 2, 3]}',
}


@pytest.mark.asyncio
async def test_unicode_round_trip(real_server):
    base, _ = real_server
    payload = {
        "client_id": "alice", "model": "m",
        "goal": SAMPLES["chinese"],
        "context": SAMPLES["japanese"],
        "tried": SAMPLES["codeblock"],
        "error": SAMPLES["tabs_newlines"],
        "constraints": SAMPLES["json_in_text"],
        "question": SAMPLES["emoji"],
    }
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as ac:
        r = await ac.post("/api/requests", json=payload)
        assert r.status_code == 201
        rid = r.json()["id"]
        d = (await ac.get(f"/api/requests/{rid}")).json()
    assert d["goal"] == SAMPLES["chinese"]
    assert d["context"] == SAMPLES["japanese"]
    assert d["tried"] == SAMPLES["codeblock"]
    assert d["error"] == SAMPLES["tabs_newlines"]
    assert d["constraints"] == SAMPLES["json_in_text"]
    assert d["question"] == SAMPLES["emoji"]


@pytest.mark.asyncio
async def test_unicode_in_answer_round_trip(real_server):
    base, _ = real_server
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as ac:
        r = await ac.post("/api/requests", json={
            "client_id": "alice", "model": "m",
            "goal": "g", "context": "c", "tried": "t",
            "error": None, "constraints": None, "question": "q",
        })
        rid = r.json()["id"]
        await ac.post(f"/api/requests/{rid}/answers", json={
            "solver_client_id": "bob", "solver_model": "m",
            "summary": SAMPLES["chinese"],
            "solution": SAMPLES["codeblock"],
            "reasoning": SAMPLES["japanese"],
            "caveats": SAMPLES["emoji"],
        })
        d = (await ac.get(f"/api/requests/{rid}")).json()
    a = d["answers"][0]
    assert a["summary"] == SAMPLES["chinese"]
    assert a["solution"] == SAMPLES["codeblock"]
    assert a["reasoning"] == SAMPLES["japanese"]
    assert a["caveats"] == SAMPLES["emoji"]

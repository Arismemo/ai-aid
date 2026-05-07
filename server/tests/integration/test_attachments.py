"""Integration tests for the attachment endpoints.

Conftest sets:
  AI_AID_MAX_ATTACHMENT_KB=256
  AI_AID_MAX_ATTACHMENTS_PER_OWNER=5
"""
import hashlib

import pytest


def _post_request(client, client_id="alice"):
    r = client.post("/api/requests", json={
        "client_id": client_id, "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _post_answer(client, rid, solver_client_id="bob"):
    r = client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": solver_client_id, "solver_model": "m",
        "summary": "s",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _upload(client, *, owner_kind, owner_id, content=b"hello world",
            filename="hello.txt", mime="text/plain", uploader="charlie"):
    files = {"file": (filename, content, mime)}
    data = {"uploader": uploader}
    if owner_kind == "request":
        url = f"/api/requests/{owner_id}/attachments"
    else:
        url = f"/api/answers/{owner_id}/attachments"
    return client.post(url, files=files, data=data)


def test_upload_to_request_returns_201_with_metadata(client):
    rid = _post_request(client)
    content = b"hello world"
    r = _upload(client, owner_kind="request", owner_id=rid, content=content)
    assert r.status_code == 201, r.text
    body = r.json()
    assert "id" in body and body["id"]
    assert body["filename"] == "hello.txt"
    assert body["size_bytes"] == len(content)
    assert body["mime"] == "text/plain"
    assert body["sha256"] == hashlib.sha256(content).hexdigest()


def test_upload_to_answer_returns_201(client):
    rid = _post_request(client, "alice")
    aid = _post_answer(client, rid, "bob")
    r = _upload(client, owner_kind="answer", owner_id=aid)
    assert r.status_code == 201, r.text
    assert r.json()["filename"] == "hello.txt"


def test_upload_to_unknown_request_returns_404(client):
    r = _upload(
        client,
        owner_kind="request",
        owner_id="00000000-0000-0000-0000-000000000000",
    )
    assert r.status_code == 404


def test_upload_to_unknown_answer_returns_404(client):
    r = _upload(
        client,
        owner_kind="answer",
        owner_id="00000000-0000-0000-0000-000000000000",
    )
    assert r.status_code == 404


def test_sixth_upload_returns_409(client):
    rid = _post_request(client)
    for i in range(5):
        r = _upload(
            client, owner_kind="request", owner_id=rid,
            content=f"file-{i}".encode(), filename=f"f{i}.txt",
        )
        assert r.status_code == 201, r.text
    r = _upload(client, owner_kind="request", owner_id=rid)
    assert r.status_code == 409
    assert r.json()["error"] == "conflict"


def test_oversized_file_returns_413(client):
    rid = _post_request(client)
    # Conftest sets cap at 256KB. Use 300KB which is under the middleware
    # ceiling (256+64 = 320) but exceeds the per-attachment limit.
    big = b"x" * (300 * 1024)
    r = _upload(client, owner_kind="request", owner_id=rid, content=big)
    assert r.status_code == 413


def test_missing_uploader_returns_400(client):
    rid = _post_request(client)
    files = {"file": ("hello.txt", b"hi", "text/plain")}
    # No data fields at all → FastAPI returns 400 (mapped from validation
    # error in the global handler) for missing required form field.
    r = client.post(f"/api/requests/{rid}/attachments", files=files)
    assert r.status_code in (400, 422)


def test_blank_uploader_returns_400(client):
    rid = _post_request(client)
    files = {"file": ("hello.txt", b"hi", "text/plain")}
    r = client.post(
        f"/api/requests/{rid}/attachments",
        files=files,
        data={"uploader": "   "},
    )
    assert r.status_code == 400


def test_get_meta_returns_metadata(client):
    rid = _post_request(client)
    up = _upload(
        client, owner_kind="request", owner_id=rid,
        content=b"abc", filename="a.txt", mime="text/plain",
        uploader="zeke",
    ).json()
    r = client.get(f"/api/attachments/{up['id']}/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == up["id"]
    assert body["owner_kind"] == "request"
    assert body["owner_id"] == rid
    assert body["filename"] == "a.txt"
    assert body["mime"] == "text/plain"
    assert body["size_bytes"] == 3
    assert body["sha256"] == hashlib.sha256(b"abc").hexdigest()
    assert body["uploader"] == "zeke"
    assert isinstance(body["created_at"], int)


def test_get_binary_returns_content_and_headers(client):
    rid = _post_request(client)
    content = b"hello bytes!"
    up = _upload(
        client, owner_kind="request", owner_id=rid,
        content=content, filename="bytes.bin",
        mime="application/octet-stream",
    ).json()
    r = client.get(f"/api/attachments/{up['id']}")
    assert r.status_code == 200
    assert r.content == content
    assert r.headers["content-type"].startswith("application/octet-stream")
    assert 'attachment; filename="bytes.bin"' in r.headers["content-disposition"]


def test_get_unknown_attachment_returns_404(client):
    r = client.get("/api/attachments/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    r = client.get("/api/attachments/00000000-0000-0000-0000-000000000000/meta")
    assert r.status_code == 404


def test_request_detail_embeds_attachments(client):
    rid = _post_request(client)
    aid = _post_answer(client, rid)
    req_att = _upload(
        client, owner_kind="request", owner_id=rid,
        content=b"req-doc", filename="req.txt",
    ).json()
    ans_att = _upload(
        client, owner_kind="answer", owner_id=aid,
        content=b"ans-doc", filename="ans.txt",
    ).json()
    r = client.get(f"/api/requests/{rid}")
    assert r.status_code == 200
    body = r.json()
    assert "attachments" in body
    assert len(body["attachments"]) == 1
    assert body["attachments"][0]["id"] == req_att["id"]
    assert body["attachments"][0]["filename"] == "req.txt"
    # Sensitive fields not leaked.
    assert "content" not in body["attachments"][0]
    # Per-answer attachments embedded.
    assert len(body["answers"]) == 1
    answer = body["answers"][0]
    assert "attachments" in answer
    assert len(answer["attachments"]) == 1
    assert answer["attachments"][0]["id"] == ans_att["id"]
    assert answer["attachments"][0]["filename"] == "ans.txt"


def test_sha256_matches_content(client):
    rid = _post_request(client)
    content = b"some-binary-payload-\x00\x01\x02"
    up = _upload(
        client, owner_kind="request", owner_id=rid, content=content,
    ).json()
    expected = hashlib.sha256(content).hexdigest()
    assert up["sha256"] == expected
    # Re-fetch via /meta — must match.
    meta = client.get(f"/api/attachments/{up['id']}/meta").json()
    assert meta["sha256"] == expected
    # Download must equal original.
    dl = client.get(f"/api/attachments/{up['id']}")
    assert dl.content == content


def test_delete_request_cascades_to_request_and_answer_attachments(client):
    rid = _post_request(client)
    aid = _post_answer(client, rid)
    req_att = _upload(
        client, owner_kind="request", owner_id=rid, content=b"r",
    ).json()
    ans_att = _upload(
        client, owner_kind="answer", owner_id=aid, content=b"a",
    ).json()

    # Both fetchable before delete.
    assert client.get(f"/api/attachments/{req_att['id']}").status_code == 200
    assert client.get(f"/api/attachments/{ans_att['id']}").status_code == 200

    r = client.delete(f"/api/requests/{rid}")
    assert r.status_code == 204

    # Both attachments now gone.
    assert client.get(f"/api/attachments/{req_att['id']}").status_code == 404
    assert client.get(f"/api/attachments/{ans_att['id']}").status_code == 404
    assert client.get(f"/api/attachments/{req_att['id']}/meta").status_code == 404
    assert client.get(f"/api/attachments/{ans_att['id']}/meta").status_code == 404


def test_separate_owners_have_independent_caps(client):
    """Filling one owner's 5-slot cap doesn't affect a sibling's."""
    rid_a = _post_request(client, "alice")
    rid_b = _post_request(client, "alex")
    for i in range(5):
        assert _upload(
            client, owner_kind="request", owner_id=rid_a,
            content=f"x{i}".encode(), filename=f"a{i}.txt",
        ).status_code == 201
    # Sibling can still upload.
    assert _upload(
        client, owner_kind="request", owner_id=rid_b,
    ).status_code == 201
    # But owner A is full.
    assert _upload(
        client, owner_kind="request", owner_id=rid_a,
    ).status_code == 409

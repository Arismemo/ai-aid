"""File attachments for requests and answers.

Routes:
  POST /api/requests/{rid}/attachments    multipart upload
  POST /api/answers/{aid}/attachments     multipart upload
  GET  /api/attachments/{att_id}          binary download
  GET  /api/attachments/{att_id}/meta     metadata only

No auth — uploader is self-reported via the `uploader` form field.
Per-file size cap: settings.max_attachment_kb (env AI_AID_MAX_ATTACHMENT_KB).
Per-owner count cap: settings.max_attachments_per_owner (default 5).
"""
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response

from ai_aid.errors import bad_request, conflict, not_found, payload_too_large

router = APIRouter()


def _meta_view(row: dict) -> dict:
    """Pick the public-metadata fields out of an attachment row."""
    return {
        "id": row["id"],
        "owner_kind": row["owner_kind"],
        "owner_id": row["owner_id"],
        "filename": row["filename"],
        "mime": row["mime"],
        "size_bytes": row["size_bytes"],
        "sha256": row["sha256"],
        "uploader": row["uploader"],
        "created_at": row["created_at"],
    }


async def _do_upload(
    *,
    request: Request,
    owner_kind: str,
    owner_id: str,
    file: UploadFile,
    uploader: Optional[str],
):
    settings = request.app.state.settings
    store = request.app.state.store

    if not uploader or not uploader.strip():
        raise bad_request("uploader is required")
    if file is None or not (file.filename or "").strip():
        raise bad_request("file is required")

    # Verify owner exists.
    if owner_kind == "request":
        if store.get_request(owner_id) is None:
            raise not_found(f"request {owner_id} not found", request_id=owner_id)
    else:
        if store.get_answer(owner_id) is None:
            raise not_found(f"answer {owner_id} not found")

    # Cap on number of attachments per owner.
    existing = store.count_attachments(owner_kind, owner_id)
    if existing >= settings.max_attachments_per_owner:
        raise conflict(
            f"owner already has {existing} attachments (max {settings.max_attachments_per_owner})",
            owner_kind=owner_kind, owner_id=owner_id,
        )

    # Read the body in full and enforce per-file size cap.
    max_bytes = settings.max_attachment_kb * 1024
    content = await file.read()
    if len(content) > max_bytes:
        raise payload_too_large(
            len(content) // 1024,
            limit_kb=settings.max_attachment_kb,
        )

    mime = (file.content_type or "application/octet-stream").strip() or "application/octet-stream"
    meta = store.add_attachment(
        owner_kind=owner_kind,
        owner_id=owner_id,
        filename=file.filename,
        mime=mime,
        content_bytes=content,
        uploader=uploader.strip(),
    )
    return meta


@router.post("/api/requests/{rid}/attachments", status_code=201)
async def upload_request_attachment(
    rid: str,
    request: Request,
    file: UploadFile = File(...),
    uploader: str = Form(...),
):
    meta = await _do_upload(
        request=request, owner_kind="request", owner_id=rid,
        file=file, uploader=uploader,
    )
    return {
        "id": meta["id"],
        "filename": meta["filename"],
        "size_bytes": meta["size_bytes"],
        "mime": meta["mime"],
        "sha256": meta["sha256"],
    }


@router.post("/api/answers/{aid}/attachments", status_code=201)
async def upload_answer_attachment(
    aid: str,
    request: Request,
    file: UploadFile = File(...),
    uploader: str = Form(...),
):
    meta = await _do_upload(
        request=request, owner_kind="answer", owner_id=aid,
        file=file, uploader=uploader,
    )
    return {
        "id": meta["id"],
        "filename": meta["filename"],
        "size_bytes": meta["size_bytes"],
        "mime": meta["mime"],
        "sha256": meta["sha256"],
    }


@router.get("/api/attachments/{att_id}/meta")
async def get_attachment_meta(att_id: str, request: Request):
    store = request.app.state.store
    row = store.get_attachment(att_id)
    if row is None:
        raise not_found(f"attachment {att_id} not found")
    return _meta_view(row)


@router.get("/api/attachments/{att_id}")
async def download_attachment(att_id: str, request: Request):
    store = request.app.state.store
    row = store.get_attachment(att_id)
    if row is None:
        raise not_found(f"attachment {att_id} not found")
    # Quote filename safely. Naive: replace double quotes with underscores.
    safe_name = (row["filename"] or "file").replace('"', "_")
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_name}"',
        "Content-Length": str(row["size_bytes"]),
    }
    return Response(
        content=row["content"],
        media_type=row["mime"] or "application/octet-stream",
        headers=headers,
    )

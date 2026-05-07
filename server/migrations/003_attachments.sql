CREATE TABLE attachments (
    id           TEXT PRIMARY KEY,
    owner_kind   TEXT NOT NULL CHECK (owner_kind IN ('request', 'answer')),
    owner_id     TEXT NOT NULL,
    filename     TEXT NOT NULL,
    mime         TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL,
    sha256       TEXT NOT NULL,
    content      BLOB NOT NULL,
    uploader     TEXT NOT NULL,
    created_at   INTEGER NOT NULL
);

CREATE INDEX idx_attachments_owner ON attachments(owner_kind, owner_id);

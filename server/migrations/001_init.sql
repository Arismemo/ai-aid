CREATE TABLE requests (
    id           TEXT PRIMARY KEY,
    client_id    TEXT NOT NULL,
    model        TEXT NOT NULL,
    goal         TEXT NOT NULL,
    context      TEXT NOT NULL,
    tried        TEXT NOT NULL,
    error        TEXT,
    constraints  TEXT,
    question     TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('open', 'closed')),
    created_at   INTEGER NOT NULL,
    closed_at    INTEGER
);

CREATE INDEX idx_requests_status ON requests(status);
CREATE INDEX idx_requests_client ON requests(client_id);
CREATE INDEX idx_requests_created ON requests(created_at DESC);

CREATE TABLE answers (
    id                TEXT PRIMARY KEY,
    request_id        TEXT NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    solver_client_id  TEXT NOT NULL,
    solver_model      TEXT NOT NULL,
    summary           TEXT NOT NULL,
    solution          TEXT,
    reasoning         TEXT,
    caveats           TEXT,
    created_at        INTEGER NOT NULL
);

CREATE INDEX idx_answers_request ON answers(request_id);

CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  INTEGER NOT NULL
);

CREATE INDEX idx_events_id ON events(id DESC);

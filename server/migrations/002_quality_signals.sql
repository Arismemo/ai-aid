ALTER TABLE requests ADD COLUMN accepted_answer_id TEXT REFERENCES answers(id) ON DELETE SET NULL;

CREATE TABLE answer_votes (
    answer_id  TEXT NOT NULL REFERENCES answers(id) ON DELETE CASCADE,
    voter      TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (answer_id, voter)
);

CREATE INDEX idx_answer_votes_answer ON answer_votes(answer_id);

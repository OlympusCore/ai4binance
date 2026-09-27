-- name: statement_01
CREATE TABLE IF NOT EXISTS execution_authorization_consumption (
                    authorization_id TEXT PRIMARY KEY,
                    single_use_nonce TEXT NOT NULL UNIQUE,
                    envelope_sha256 TEXT NOT NULL,
                    preview_hash TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    claimed_at TEXT NOT NULL
                )

-- name: statement_02
BEGIN IMMEDIATE

-- name: statement_03
INSERT INTO execution_authorization_consumption (
                    authorization_id,
                    single_use_nonce,
                    envelope_sha256,
                    preview_hash,
                    execution_id,
                    claimed_at
                ) VALUES (?, ?, ?, ?, ?, ?)

-- name: statement_04
SELECT authorization_id, single_use_nonce, envelope_sha256,
                       preview_hash, execution_id, claimed_at
                FROM execution_authorization_consumption
                WHERE authorization_id = ?

-- name: statement_05
COMMIT

-- name: statement_06
ROLLBACK

-- name: statement_07
ROLLBACK

-- name: statement_08
SELECT 1
                        FROM execution_authorization_consumption
                        WHERE authorization_id = ?

-- name: statement_01
CREATE TABLE IF NOT EXISTS capability_leases (
    lease_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    project TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    permission TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    scope_hash TEXT NOT NULL DEFAULT '',
    consumed_at TEXT,
    execution_id TEXT UNIQUE
)

-- name: statement_02
INSERT INTO capability_leases (
                        lease_id, run_id, project, tool_name, permission, policy_hash,
                        issued_at, expires_at, scope_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

-- name: statement_03
SELECT run_id, project, tool_name, permission, policy_hash,
                           issued_at, expires_at, scope_hash, consumed_at
                    FROM capability_leases WHERE lease_id = ?

-- name: statement_04
UPDATE capability_leases
                        SET consumed_at = ?, execution_id = ?
                        WHERE lease_id = ? AND consumed_at IS NULL

-- name: statement_05
SELECT run_id, project, tool_name, permission, policy_hash,
                           issued_at, expires_at, scope_hash, consumed_at, execution_id
                    FROM capability_leases WHERE lease_id = ?

-- name: statement_06
PRAGMA table_info(capability_leases)

-- name: statement_07
ALTER TABLE capability_leases ADD COLUMN scope_hash TEXT NOT NULL DEFAULT ''

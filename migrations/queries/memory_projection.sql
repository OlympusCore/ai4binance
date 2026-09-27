-- name: statement_01
INSERT INTO memory_records (
                            memory_id, content_hash, status, subject_key, memory_type,
                            classification, market_type, symbol, strategy_id,
                            setup_type,
                            recorded_at, valid_from, valid_until, payload
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

-- name: statement_02
INSERT INTO memory_fts (memory_id, body) VALUES (?, ?)

-- name: statement_03
INSERT INTO projection_metadata (key, value) VALUES (?, ?)

-- name: statement_04
SELECT payload FROM memory_records ORDER BY memory_id

-- name: statement_05
SELECT records.payload
                FROM memory_fts
                INNER JOIN memory_records AS records
                    ON records.memory_id = memory_fts.memory_id
                WHERE memory_fts MATCH ?
                ORDER BY bm25(memory_fts), records.memory_id
                LIMIT ?

-- name: statement_06
SELECT key, value FROM projection_metadata

-- name: statement_07
SELECT COUNT(*) FROM memory_records

-- name: statement_08
CREATE TABLE projection_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE memory_records (
            memory_id TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            subject_key TEXT NOT NULL,
            memory_type TEXT NOT NULL,
            classification TEXT NOT NULL,
            market_type TEXT,
            symbol TEXT,
            strategy_id TEXT,
            setup_type TEXT,
            recorded_at TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_until TEXT,
            payload TEXT NOT NULL
        );
        CREATE INDEX memory_records_temporal_idx
            ON memory_records (recorded_at, valid_from, valid_until);
        CREATE INDEX memory_records_entity_idx
            ON memory_records (subject_key, market_type, symbol, strategy_id);
        CREATE VIRTUAL TABLE memory_fts USING fts5(memory_id UNINDEXED, body);

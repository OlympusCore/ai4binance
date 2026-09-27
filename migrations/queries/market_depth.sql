-- name: statement_01
PRAGMA journal_mode=WAL

-- name: statement_02
PRAGMA synchronous=FULL

-- name: statement_03
CREATE TABLE IF NOT EXISTS depth_events (
                seq INTEGER PRIMARY KEY, market TEXT NOT NULL, symbol TEXT NOT NULL,
                kind TEXT NOT NULL, payload BLOB NOT NULL, received_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS depth_stream ON depth_events(market,symbol,seq);
            CREATE TABLE IF NOT EXISTS depth_heads (
                market TEXT, symbol TEXT, checkpoint_seq INTEGER, latest_seq INTEGER,
                status TEXT, received_at REAL, PRIMARY KEY(market,symbol));

-- name: statement_04
INSERT INTO depth_events(market,symbol,kind,payload,received_at) VALUES(?,?,?,?,?)

-- name: statement_05
INSERT INTO depth_heads VALUES(?,?,?,?,?,?)
                    ON CONFLICT(market,symbol) DO UPDATE SET
                    checkpoint_seq=COALESCE(excluded.checkpoint_seq,depth_heads.checkpoint_seq),
                    latest_seq=excluded.latest_seq,status=excluded.status,received_at=excluded.received_at

-- name: statement_06
DELETE FROM depth_events WHERE seq IN (SELECT seq FROM depth_events WHERE market=? AND symbol=? AND seq<? ORDER BY seq LIMIT ?)

-- name: statement_07
SELECT market,symbol FROM depth_heads UNION SELECT DISTINCT market,symbol FROM depth_events

-- name: statement_08
DELETE FROM depth_events WHERE market=? AND symbol=?

-- name: statement_09
DELETE FROM depth_heads WHERE market=? AND symbol=?

-- name: statement_10
BEGIN

-- name: statement_11
SELECT checkpoint_seq,latest_seq,status,received_at FROM depth_heads WHERE market=? AND symbol=?

-- name: statement_12
SELECT kind,payload FROM depth_events WHERE market=? AND symbol=? AND seq>=? AND seq<=? ORDER BY seq LIMIT 100001

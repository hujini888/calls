import sqlite3
import time
from pathlib import Path
from typing import List, Optional

from .models import PairSnapshot, Watch


class Database:
    def __init__(self, path: Path):
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS watches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                chain_id TEXT NOT NULL,
                token_address TEXT NOT NULL,
                pair_address TEXT NOT NULL,
                symbol TEXT NOT NULL,
                quote_symbol TEXT NOT NULL,
                dex_id TEXT NOT NULL,
                threshold_percent REAL NOT NULL,
                window_seconds INTEGER NOT NULL,
                min_liquidity_usd REAL NOT NULL,
                cooldown_seconds INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                UNIQUE(chat_id, chain_id, token_address)
            );

            CREATE TABLE IF NOT EXISTS alert_state (
                watch_id INTEGER PRIMARY KEY,
                last_up_at REAL,
                last_down_at REAL,
                FOREIGN KEY(watch_id) REFERENCES watches(id) ON DELETE CASCADE
            );
            """
        )
        self.connection.commit()

    @staticmethod
    def _watch(row: sqlite3.Row) -> Watch:
        return Watch(
            id=row["id"],
            chat_id=row["chat_id"],
            chain_id=row["chain_id"],
            token_address=row["token_address"],
            pair_address=row["pair_address"],
            symbol=row["symbol"],
            quote_symbol=row["quote_symbol"],
            dex_id=row["dex_id"],
            threshold_percent=row["threshold_percent"],
            window_seconds=row["window_seconds"],
            min_liquidity_usd=row["min_liquidity_usd"],
            cooldown_seconds=row["cooldown_seconds"],
            enabled=bool(row["enabled"]),
        )

    def add_watch(
        self,
        chat_id: int,
        snapshot: PairSnapshot,
        threshold_percent: float,
        window_seconds: int,
        min_liquidity_usd: float,
        cooldown_seconds: int,
    ) -> Watch:
        self.connection.execute(
            """
            INSERT INTO watches (
                chat_id, chain_id, token_address, pair_address, symbol,
                quote_symbol, dex_id, threshold_percent, window_seconds,
                min_liquidity_usd, cooldown_seconds, enabled, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(chat_id, chain_id, token_address) DO UPDATE SET
                pair_address=excluded.pair_address,
                symbol=excluded.symbol,
                quote_symbol=excluded.quote_symbol,
                dex_id=excluded.dex_id,
                threshold_percent=excluded.threshold_percent,
                window_seconds=excluded.window_seconds,
                min_liquidity_usd=excluded.min_liquidity_usd,
                cooldown_seconds=excluded.cooldown_seconds,
                enabled=1
            """,
            (
                chat_id,
                snapshot.chain_id,
                snapshot.token_address,
                snapshot.pair_address,
                snapshot.symbol,
                snapshot.quote_symbol,
                snapshot.dex_id,
                threshold_percent,
                window_seconds,
                min_liquidity_usd,
                cooldown_seconds,
                int(time.time()),
            ),
        )
        self.connection.commit()
        row = self.connection.execute(
            "SELECT * FROM watches WHERE chat_id=? AND chain_id=? AND token_address=?",
            (chat_id, snapshot.chain_id, snapshot.token_address),
        ).fetchone()
        return self._watch(row)

    def list_watches(self, chat_id: Optional[int] = None, enabled_only: bool = False) -> List[Watch]:
        clauses = []
        params = []
        if chat_id is not None:
            clauses.append("chat_id=?")
            params.append(chat_id)
        if enabled_only:
            clauses.append("enabled=1")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.connection.execute(
            f"SELECT * FROM watches{where} ORDER BY id", params
        ).fetchall()
        return [self._watch(row) for row in rows]

    def get_watch(self, chat_id: int, watch_id: int) -> Optional[Watch]:
        row = self.connection.execute(
            "SELECT * FROM watches WHERE chat_id=? AND id=?", (chat_id, watch_id)
        ).fetchone()
        return self._watch(row) if row else None

    def set_enabled(self, chat_id: int, watch_id: int, enabled: bool) -> bool:
        cursor = self.connection.execute(
            "UPDATE watches SET enabled=? WHERE chat_id=? AND id=?",
            (int(enabled), chat_id, watch_id),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def delete_watch(self, chat_id: int, watch_id: int) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM watches WHERE chat_id=? AND id=?", (chat_id, watch_id)
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def update_pair(self, watch_id: int, snapshot: PairSnapshot) -> None:
        self.connection.execute(
            """
            UPDATE watches SET pair_address=?, symbol=?, quote_symbol=?, dex_id=?
            WHERE id=?
            """,
            (
                snapshot.pair_address,
                snapshot.symbol,
                snapshot.quote_symbol,
                snapshot.dex_id,
                watch_id,
            ),
        )
        self.connection.commit()

    def get_last_alerts(self, watch_id: int):
        row = self.connection.execute(
            "SELECT last_up_at, last_down_at FROM alert_state WHERE watch_id=?", (watch_id,)
        ).fetchone()
        if not row:
            return None, None
        return row["last_up_at"], row["last_down_at"]

    def set_last_alert(self, watch_id: int, direction: str, timestamp: float) -> None:
        column = "last_up_at" if direction == "up" else "last_down_at"
        self.connection.execute(
            "INSERT OR IGNORE INTO alert_state(watch_id) VALUES (?)", (watch_id,)
        )
        self.connection.execute(
            f"UPDATE alert_state SET {column}=? WHERE watch_id=?", (timestamp, watch_id)
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


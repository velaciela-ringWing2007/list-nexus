"""SQLite接続とスキーマ初期化.

Streamlitはリクエストごとにスクリプトを再実行し、複数スレッドから
呼ばれることがあるため、接続は長期間保持せず操作単位で開閉する。
登録件数は多くても数百件を想定しており、この方式で十分速い。
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from constants import DATABASE_PATH

SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    list_url TEXT NOT NULL UNIQUE,
    new_item_url TEXT,
    settings_url TEXT,
    site_name TEXT NOT NULL DEFAULT '',
    group_name TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    environment TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    favorite INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    open_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lists_group_name ON lists (group_name);
CREATE INDEX IF NOT EXISTS idx_lists_favorite ON lists (favorite);
"""


class DatabaseError(RuntimeError):
    """データベース操作に失敗した場合に送出する例外."""


def _ensure_parent_dir(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)


def open_connection(db_path: Path | str = DATABASE_PATH) -> sqlite3.Connection:
    """SQLite接続を開いて返す。呼び出し側が close する責任を持つ。"""
    path = Path(db_path)
    _ensure_parent_dir(path)
    try:
        connection = sqlite3.connect(path, timeout=10.0)
    except sqlite3.Error as exc:
        raise DatabaseError(f"データベースに接続できませんでした: {path}") from exc

    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")
    except sqlite3.Error as exc:
        connection.close()
        raise DatabaseError("データベースの初期設定に失敗しました。") from exc
    return connection


@contextmanager
def connect(db_path: Path | str = DATABASE_PATH) -> Iterator[sqlite3.Connection]:
    """接続を開き、処理終了後に必ず閉じるコンテキストマネージャ。"""
    connection = open_connection(db_path)
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """成功時にcommit、例外時にrollbackするコンテキストマネージャ。"""
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()


def initialize_database(db_path: Path | str = DATABASE_PATH) -> None:
    """DBファイルとテーブルを作成する。既に存在する場合は何もしない。"""
    try:
        with connect(db_path) as connection, transaction(connection):
            connection.executescript(SCHEMA_SQL)
    except sqlite3.Error as exc:
        raise DatabaseError("データベースの初期化に失敗しました。") from exc

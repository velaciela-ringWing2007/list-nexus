"""listsテーブルへのデータアクセス層.

SQLはこのモジュールに閉じ込め、UI層からSQLite接続を直接扱わない。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable, Sequence

from constants import (
    DUPLICATE_ERROR,
    DUPLICATE_SKIP,
    DUPLICATE_UPDATE,
    UNCATEGORIZED_GROUP,
)
from database import DatabaseError, connect, initialize_database, transaction
from models import (
    SharePointList,
    list_to_params,
    now_iso,
    row_to_list,
)

_SELECT_COLUMNS = """
    id, name, list_url, new_item_url, settings_url, site_name, group_name,
    tags, environment, description, favorite, sort_order, open_count,
    created_at, updated_at
"""

# 既定の並び順: お気に入り → 表示順 → 名前
_DEFAULT_ORDER = "ORDER BY favorite DESC, sort_order ASC, name COLLATE NOCASE ASC"


class DuplicateUrlError(ValueError):
    """一覧URLが既に登録されている場合に送出する例外."""

    def __init__(self, list_url: str, existing: SharePointList | None = None) -> None:
        super().__init__(f"この一覧URLは既に登録されています: {list_url}")
        self.list_url = list_url
        self.existing = existing


class ListRepository:
    """SharePoint Listリンク情報のリポジトリ."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    # ------------------------------------------------------------------
    # 初期化
    # ------------------------------------------------------------------
    def initialize(self) -> None:
        """DBファイルとテーブルを用意する。"""
        initialize_database(self.db_path)

    # ------------------------------------------------------------------
    # 取得
    # ------------------------------------------------------------------
    def list_all(self) -> list[SharePointList]:
        """全件を既定の並び順で取得する。"""
        with connect(self.db_path) as connection:
            rows = connection.execute(
                f"SELECT {_SELECT_COLUMNS} FROM lists {_DEFAULT_ORDER}"
            ).fetchall()
        return [row_to_list(row) for row in rows]

    def get_by_id(self, list_id: int) -> SharePointList | None:
        """ID指定で1件取得する。存在しなければ None を返す。"""
        with connect(self.db_path) as connection:
            row = connection.execute(
                f"SELECT {_SELECT_COLUMNS} FROM lists WHERE id = ?", (list_id,)
            ).fetchone()
        return row_to_list(row) if row else None

    def get_by_url(self, list_url: str) -> SharePointList | None:
        """一覧URL指定で1件取得する。存在しなければ None を返す。"""
        with connect(self.db_path) as connection:
            row = connection.execute(
                f"SELECT {_SELECT_COLUMNS} FROM lists WHERE list_url = ?",
                (list_url.strip(),),
            ).fetchone()
        return row_to_list(row) if row else None

    def count(self) -> int:
        """登録件数を返す。"""
        with connect(self.db_path) as connection:
            row = connection.execute("SELECT COUNT(*) AS n FROM lists").fetchone()
        return int(row["n"])

    # ------------------------------------------------------------------
    # 登録・更新・削除
    # ------------------------------------------------------------------
    def create(self, item: SharePointList) -> SharePointList:
        """新規登録し、採番されたIDを含むモデルを返す。"""
        timestamp = now_iso()
        record = replace(item, created_at=timestamp, updated_at=timestamp)
        params = list_to_params(record)

        try:
            with connect(self.db_path) as connection, transaction(connection):
                cursor = connection.execute(
                    """
                    INSERT INTO lists (
                        name, list_url, new_item_url, settings_url, site_name,
                        group_name, tags, environment, description, favorite,
                        sort_order, open_count, created_at, updated_at
                    ) VALUES (
                        :name, :list_url, :new_item_url, :settings_url, :site_name,
                        :group_name, :tags, :environment, :description, :favorite,
                        :sort_order, :open_count, :created_at, :updated_at
                    )
                    """,
                    params,
                )
                new_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            if "list_url" in str(exc):
                raise DuplicateUrlError(item.list_url, self.get_by_url(item.list_url)) from exc
            raise DatabaseError("リストの登録に失敗しました。") from exc
        except sqlite3.Error as exc:
            raise DatabaseError("リストの登録に失敗しました。") from exc

        return replace(record, id=new_id)

    def update(self, item: SharePointList) -> SharePointList:
        """既存レコードを更新する。open_count と created_at は変更しない。"""
        if item.id is None:
            raise ValueError("更新対象のIDが指定されていません。")

        record = replace(item, updated_at=now_iso())
        params = list_to_params(record)
        params["id"] = record.id

        try:
            with connect(self.db_path) as connection, transaction(connection):
                cursor = connection.execute(
                    """
                    UPDATE lists SET
                        name = :name,
                        list_url = :list_url,
                        new_item_url = :new_item_url,
                        settings_url = :settings_url,
                        site_name = :site_name,
                        group_name = :group_name,
                        tags = :tags,
                        environment = :environment,
                        description = :description,
                        favorite = :favorite,
                        sort_order = :sort_order,
                        updated_at = :updated_at
                    WHERE id = :id
                    """,
                    params,
                )
                if cursor.rowcount == 0:
                    raise DatabaseError("更新対象のリストが見つかりませんでした。")
        except sqlite3.IntegrityError as exc:
            if "list_url" in str(exc):
                raise DuplicateUrlError(item.list_url, self.get_by_url(item.list_url)) from exc
            raise DatabaseError("リストの更新に失敗しました。") from exc
        except sqlite3.Error as exc:
            raise DatabaseError("リストの更新に失敗しました。") from exc

        return record

    def delete(self, list_id: int) -> bool:
        """物理削除する。削除した場合 True を返す。"""
        try:
            with connect(self.db_path) as connection, transaction(connection):
                cursor = connection.execute("DELETE FROM lists WHERE id = ?", (list_id,))
                return cursor.rowcount > 0
        except sqlite3.Error as exc:
            raise DatabaseError("リストの削除に失敗しました。") from exc

    def delete_many(self, list_ids: Sequence[int]) -> int:
        """複数件をまとめて物理削除し、削除件数を返す。

        1トランザクションで実行するため、途中で失敗した場合は1件も削除しない。
        """
        ids = [int(value) for value in list_ids]
        if not ids:
            return 0
        try:
            with connect(self.db_path) as connection, transaction(connection):
                cursor = connection.executemany(
                    "DELETE FROM lists WHERE id = ?", [(list_id,) for list_id in ids]
                )
                return int(cursor.rowcount)
        except sqlite3.Error as exc:
            raise DatabaseError("リストの一括削除に失敗しました。") from exc

    def set_favorite(self, list_id: int, favorite: bool) -> bool:
        """お気に入り状態を更新する。更新した場合 True を返す。"""
        try:
            with connect(self.db_path) as connection, transaction(connection):
                cursor = connection.execute(
                    "UPDATE lists SET favorite = ?, updated_at = ? WHERE id = ?",
                    (1 if favorite else 0, now_iso(), list_id),
                )
                return cursor.rowcount > 0
        except sqlite3.Error as exc:
            raise DatabaseError("お気に入りの更新に失敗しました。") from exc

    def increment_open_count(self, list_id: int) -> None:
        """一覧を開いた回数を1加算する。

        ブラウザ側のリンククリックは検知できないため、アプリ内の
        専用操作から呼ばれたときだけ加算する。
        """
        try:
            with connect(self.db_path) as connection, transaction(connection):
                connection.execute(
                    "UPDATE lists SET open_count = open_count + 1 WHERE id = ?",
                    (list_id,),
                )
        except sqlite3.Error as exc:
            raise DatabaseError("オープン回数の更新に失敗しました。") from exc

    # ------------------------------------------------------------------
    # 集計
    # ------------------------------------------------------------------
    def group_names(self) -> list[str]:
        """登録済みのグループ名を昇順で返す（空グループは含めない）。"""
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT group_name FROM lists
                WHERE TRIM(group_name) <> ''
                ORDER BY group_name COLLATE NOCASE ASC
                """
            ).fetchall()
        return [row["group_name"] for row in rows]

    def tag_names(self) -> list[str]:
        """登録済みのタグを重複なく昇順で返す。"""
        tags: set[str] = set()
        for item in self.list_all():
            tags.update(item.tags)
        return sorted(tags, key=lambda tag: tag.casefold())

    def environments(self) -> list[str]:
        """実際に使われている環境の内部値を返す（未設定は含めない）。"""
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT environment FROM lists
                WHERE TRIM(environment) <> ''
                ORDER BY environment ASC
                """
            ).fetchall()
        return [row["environment"] for row in rows]


# ----------------------------------------------------------------------
# インポートの保存（重複時の動作を適用する）
# ----------------------------------------------------------------------
@dataclass(slots=True)
class ImportSummary:
    """インポート結果の集計."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def saved(self) -> int:
        return self.created + self.updated


def save_import_items(
    repository: ListRepository,
    items: Sequence[SharePointList],
    policy: str = DUPLICATE_SKIP,
) -> ImportSummary:
    """検証済みのリストを保存する。一覧URLが重複する場合は policy に従う。

    - DUPLICATE_SKIP: 既存を残して読み飛ばす
    - DUPLICATE_UPDATE: 既存レコードを上書きする
    - DUPLICATE_ERROR: エラーとして記録し、保存しない
    """
    summary = ImportSummary()

    for item in items:
        existing = repository.get_by_url(item.list_url)
        try:
            if existing is None:
                repository.create(item)
                summary.created += 1
            elif policy == DUPLICATE_UPDATE:
                repository.update(replace(item, id=existing.id))
                summary.updated += 1
            elif policy == DUPLICATE_ERROR:
                summary.errors.append(
                    f"{item.name}: 一覧URLが既に登録されています（{existing.name}）。"
                )
            else:  # DUPLICATE_SKIP
                summary.skipped += 1
        except (DuplicateUrlError, DatabaseError) as exc:
            summary.errors.append(f"{item.name}: {exc}")

    return summary


# ----------------------------------------------------------------------
# 取得結果に対する絞り込み（SQLを増やさずPython側で行う）
# ----------------------------------------------------------------------
def matches_query(item: SharePointList, query: str) -> bool:
    """検索語がリストのいずれかの項目に部分一致するかを返す。

    大文字・小文字を区別せず、日本語を含む部分一致で判定する。
    """
    needle = query.strip().casefold()
    if not needle:
        return True

    haystacks: list[str] = [
        item.name,
        item.site_name,
        item.group_name,
        item.description,
        item.list_url,
        *item.tags,
    ]
    return any(needle in value.casefold() for value in haystacks if value)


def filter_lists(
    items: Iterable[SharePointList],
    *,
    query: str = "",
    favorites_only: bool = False,
    groups: Sequence[str] = (),
    tags: Sequence[str] = (),
    environments: Sequence[str] = (),
) -> list[SharePointList]:
    """複数条件（AND）でリストを絞り込む。"""
    group_set = set(groups)
    tag_set = set(tags)
    environment_set = set(environments)

    result: list[SharePointList] = []
    for item in items:
        if favorites_only and not item.favorite:
            continue
        if group_set and (item.group_name or UNCATEGORIZED_GROUP) not in group_set:
            continue
        if tag_set and not tag_set.intersection(item.tags):
            continue
        if environment_set and item.environment not in environment_set:
            continue
        if not matches_query(item, query):
            continue
        result.append(item)
    return result


def group_by_group_name(
    items: Iterable[SharePointList],
) -> list[tuple[str, list[SharePointList]]]:
    """グループ名ごとにまとめる。未分類は最後に置く。"""
    buckets: dict[str, list[SharePointList]] = {}
    for item in items:
        key = item.group_name.strip() or UNCATEGORIZED_GROUP
        buckets.setdefault(key, []).append(item)

    named = sorted(
        (key for key in buckets if key != UNCATEGORIZED_GROUP),
        key=lambda key: key.casefold(),
    )
    ordered = [(key, buckets[key]) for key in named]
    if UNCATEGORIZED_GROUP in buckets:
        ordered.append((UNCATEGORIZED_GROUP, buckets[UNCATEGORIZED_GROUP]))
    return ordered

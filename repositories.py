"""listsテーブルへのデータアクセス層.

SQLはこのモジュールに閉じ込め、UI層からSQLite接続を直接扱わない。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable, Sequence

from constants import (
    DEFAULT_SPACE,
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
    id, name, space, list_url, new_item_url, settings_url, site_name, group_name,
    tags, environment, description, favorite, sort_order, open_count,
    created_at, updated_at
"""

# 既定の並び順: お気に入り → 表示順 → 名前
_DEFAULT_ORDER = "ORDER BY favorite DESC, sort_order ASC, name COLLATE NOCASE ASC"


class SpaceError(ValueError):
    """タブの操作が行えない場合に送出する例外."""


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
    def list_all(self, space: str | None = None) -> list[SharePointList]:
        """全件を既定の並び順で取得する。space を指定するとそのタブだけ返す。"""
        where = "WHERE space = ?" if space is not None else ""
        params = (space,) if space is not None else ()
        with connect(self.db_path) as connection:
            rows = connection.execute(
                f"SELECT {_SELECT_COLUMNS} FROM lists {where} {_DEFAULT_ORDER}", params
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

    def count(self, space: str | None = None) -> int:
        """登録件数を返す。space を指定するとそのタブの件数を返す。"""
        where = "WHERE space = ?" if space is not None else ""
        params = (space,) if space is not None else ()
        with connect(self.db_path) as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS n FROM lists {where}", params
            ).fetchone()
        return int(row["n"])

    def count_by_space(self) -> dict[str, int]:
        """タブごとの件数を返す。"""
        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT space, COUNT(*) AS n FROM lists GROUP BY space"
            ).fetchall()
        return {row["space"]: int(row["n"]) for row in rows}

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
                        name, space, list_url, new_item_url, settings_url, site_name,
                        group_name, tags, environment, description, favorite,
                        sort_order, open_count, created_at, updated_at
                    ) VALUES (
                        :name, :space, :list_url, :new_item_url, :settings_url, :site_name,
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
                        space = :space,
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
    def group_names(self, space: str | None = None) -> list[str]:
        """登録済みのグループ名を昇順で返す（空グループは含めない）。"""
        clause = "AND space = ?" if space is not None else ""
        params = (space,) if space is not None else ()
        with connect(self.db_path) as connection:
            rows = connection.execute(
                f"""
                SELECT DISTINCT group_name FROM lists
                WHERE TRIM(group_name) <> '' {clause}
                ORDER BY group_name COLLATE NOCASE ASC
                """,
                params,
            ).fetchall()
        return [row["group_name"] for row in rows]

    def tag_names(self, space: str | None = None) -> list[str]:
        """登録済みのタグを重複なく昇順で返す。"""
        tags: set[str] = set()
        for item in self.list_all(space):
            tags.update(item.tags)
        return sorted(tags, key=lambda tag: tag.casefold())

    def environments(self, space: str | None = None) -> list[str]:
        """実際に使われている環境の内部値を返す（未設定は含めない）。"""
        clause = "AND space = ?" if space is not None else ""
        params = (space,) if space is not None else ()
        with connect(self.db_path) as connection:
            rows = connection.execute(
                f"""
                SELECT DISTINCT environment FROM lists
                WHERE TRIM(environment) <> '' {clause}
                ORDER BY environment ASC
                """,
                params,
            ).fetchall()
        return [row["environment"] for row in rows]

    # ------------------------------------------------------------------
    # タブ（space）
    # ------------------------------------------------------------------
    def spaces(self) -> list[str]:
        """タブ名を表示順で返す。"""
        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT name FROM spaces ORDER BY sort_order ASC, name COLLATE NOCASE ASC"
            ).fetchall()
        return [row["name"] for row in rows]

    def add_space(self, name: str) -> str:
        """タブを追加する。既にあれば何もしない。"""
        space = (name or "").strip()
        if not space:
            raise SpaceError("タブ名を入力してください。")
        try:
            with connect(self.db_path) as connection, transaction(connection):
                row = connection.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next FROM spaces"
                ).fetchone()
                connection.execute(
                    "INSERT OR IGNORE INTO spaces (name, sort_order, created_at)"
                    " VALUES (?, ?, ?)",
                    (space, int(row["next"]), now_iso()),
                )
        except sqlite3.Error as exc:
            raise DatabaseError("タブの追加に失敗しました。") from exc
        return space

    def rename_space(self, old_name: str, new_name: str) -> int:
        """タブ名を変更し、所属するリストもまとめて付け替える。"""
        source = (old_name or "").strip()
        target = (new_name or "").strip()
        if not target:
            raise SpaceError("新しいタブ名を入力してください。")
        if source == target:
            return 0
        if target in self.spaces():
            raise SpaceError(f"「{target}」は既に存在します。")

        try:
            with connect(self.db_path) as connection, transaction(connection):
                connection.execute("UPDATE spaces SET name = ? WHERE name = ?", (target, source))
                cursor = connection.execute(
                    "UPDATE lists SET space = ?, updated_at = ? WHERE space = ?",
                    (target, now_iso(), source),
                )
                return int(cursor.rowcount)
        except sqlite3.Error as exc:
            raise DatabaseError("タブ名の変更に失敗しました。") from exc

    def delete_space(self, name: str, move_to: str | None = None) -> int:
        """タブを削除する。

        move_to を指定すると中身をそのタブへ移し、指定しない場合は中身も削除する。
        最後の1つは削除できない。
        """
        space = (name or "").strip()
        existing = self.spaces()
        if space not in existing:
            raise SpaceError(f"「{space}」は存在しません。")
        if len(existing) <= 1:
            raise SpaceError("最後のタブは削除できません。")
        if move_to is not None and move_to not in existing:
            raise SpaceError(f"移動先の「{move_to}」が見つかりません。")

        try:
            with connect(self.db_path) as connection, transaction(connection):
                if move_to is None:
                    cursor = connection.execute("DELETE FROM lists WHERE space = ?", (space,))
                else:
                    cursor = connection.execute(
                        "UPDATE lists SET space = ?, updated_at = ? WHERE space = ?",
                        (move_to, now_iso(), space),
                    )
                affected = int(cursor.rowcount)
                connection.execute("DELETE FROM spaces WHERE name = ?", (space,))
                return affected
        except sqlite3.Error as exc:
            raise DatabaseError("タブの削除に失敗しました。") from exc

    def reorder_spaces(self, names: Sequence[str]) -> None:
        """タブの表示順を指定された並びで保存する。"""
        try:
            with connect(self.db_path) as connection, transaction(connection):
                connection.executemany(
                    "UPDATE spaces SET sort_order = ? WHERE name = ?",
                    [(index, name) for index, name in enumerate(names)],
                )
        except sqlite3.Error as exc:
            raise DatabaseError("タブの並べ替えに失敗しました。") from exc

    def move_to_space(self, list_ids: Sequence[int], space: str) -> int:
        """選択したリストを別のタブへ移動する。"""
        ids = [int(value) for value in list_ids]
        if not ids:
            return 0
        if space not in self.spaces():
            raise SpaceError(f"移動先の「{space}」が見つかりません。")
        try:
            with connect(self.db_path) as connection, transaction(connection):
                cursor = connection.executemany(
                    "UPDATE lists SET space = ?, updated_at = ? WHERE id = ?",
                    [(space, now_iso(), list_id) for list_id in ids],
                )
                return int(cursor.rowcount)
        except sqlite3.Error as exc:
            raise DatabaseError("タブの移動に失敗しました。") from exc


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

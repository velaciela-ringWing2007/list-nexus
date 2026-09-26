"""repositories のテスト（一時SQLite DBを使用）."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from constants import DUPLICATE_ERROR, DUPLICATE_SKIP, DUPLICATE_UPDATE
from database import DatabaseError, connect, transaction
from import_parser import parse_json_text
from models import (
    SharePointList,
    ValidationError,
    build_list,
    tags_from_json,
    to_export_dict,
)
from repositories import (
    DuplicateUrlError,
    ListRepository,
    filter_lists,
    group_by_group_name,
    matches_query,
    save_import_items,
)

ISSUES_URL = "https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx"
DEVICES_URL = "https://example.sharepoint.com/sites/dev/Lists/Devices/AllItems.aspx"
MEMO_URL = "https://example.sharepoint.com/sites/soumu/Lists/Memo/AllItems.aspx"


@pytest.fixture()
def repo(tmp_path: Path) -> ListRepository:
    repository = ListRepository(tmp_path / "test.sqlite3")
    repository.initialize()
    return repository


def make_list(**overrides: object) -> SharePointList:
    values: dict[str, object] = {
        "name": "障害管理",
        "list_url": ISSUES_URL,
        "site_name": "開発部",
        "group_name": "開発",
        "tags": "障害, 本番",
        "environment": "production",
        "description": "障害の記録",
    }
    values.update(overrides)
    return build_list(**values)  # type: ignore[arg-type]


class TestInitialize:
    def test_creates_database_file_and_table(self, tmp_path: Path) -> None:
        db_path = tmp_path / "nested" / "test.sqlite3"
        ListRepository(db_path).initialize()
        assert db_path.exists()
        with connect(db_path) as connection:
            row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='lists'"
            ).fetchone()
        assert row is not None

    def test_initialize_is_idempotent(self, repo: ListRepository) -> None:
        repo.create(make_list())
        repo.initialize()
        assert repo.count() == 1


class TestCrud:
    def test_create_assigns_id_and_timestamps(self, repo: ListRepository) -> None:
        created = repo.create(make_list())
        assert created.id is not None
        assert created.created_at
        assert created.updated_at == created.created_at

    def test_get_by_id(self, repo: ListRepository) -> None:
        created = repo.create(make_list())
        fetched = repo.get_by_id(created.id or 0)
        assert fetched is not None
        assert fetched.name == "障害管理"
        assert fetched.tags == ["障害", "本番"]
        assert fetched.environment == "production"

    def test_get_by_id_missing_returns_none(self, repo: ListRepository) -> None:
        assert repo.get_by_id(999) is None

    def test_get_by_url(self, repo: ListRepository) -> None:
        repo.create(make_list())
        fetched = repo.get_by_url(f"  {ISSUES_URL}  ")
        assert fetched is not None
        assert fetched.list_url == ISSUES_URL

    def test_get_by_url_missing_returns_none(self, repo: ListRepository) -> None:
        assert repo.get_by_url(DEVICES_URL) is None

    def test_update_changes_fields_and_timestamp(self, repo: ListRepository) -> None:
        created = repo.create(make_list())
        modified = build_list(
            id=created.id,
            name="障害管理（改）",
            list_url=ISSUES_URL,
            group_name="運用",
            tags=["運用"],
            environment="staging",
        )
        updated = repo.update(modified)
        stored = repo.get_by_id(created.id or 0)
        assert stored is not None
        assert stored.name == "障害管理（改）"
        assert stored.group_name == "運用"
        assert stored.tags == ["運用"]
        assert stored.environment == "staging"
        assert updated.updated_at >= created.updated_at

    def test_update_keeps_created_at_and_open_count(self, repo: ListRepository) -> None:
        created = repo.create(make_list())
        repo.increment_open_count(created.id or 0)
        repo.update(build_list(id=created.id, name="別名", list_url=ISSUES_URL))
        stored = repo.get_by_id(created.id or 0)
        assert stored is not None
        assert stored.created_at == created.created_at
        assert stored.open_count == 1

    def test_update_without_id_raises(self, repo: ListRepository) -> None:
        with pytest.raises(ValueError):
            repo.update(make_list())

    def test_update_missing_row_raises(self, repo: ListRepository) -> None:
        with pytest.raises(DatabaseError):
            repo.update(build_list(id=999, name="x", list_url=ISSUES_URL))

    def test_delete(self, repo: ListRepository) -> None:
        created = repo.create(make_list())
        assert repo.delete(created.id or 0) is True
        assert repo.get_by_id(created.id or 0) is None
        assert repo.count() == 0

    def test_delete_missing_returns_false(self, repo: ListRepository) -> None:
        assert repo.delete(999) is False


class TestDeleteMany:
    def test_deletes_selected_ids_only(self, repo: ListRepository) -> None:
        first = repo.create(make_list())
        second = repo.create(make_list(name="端末管理", list_url=DEVICES_URL))
        third = repo.create(make_list(name="総務メモ", list_url=MEMO_URL))

        deleted = repo.delete_many([first.id or 0, third.id or 0])
        assert deleted == 2
        remaining = [item.name for item in repo.list_all()]
        assert remaining == ["端末管理"]
        assert repo.get_by_id(second.id or 0) is not None

    def test_empty_list_deletes_nothing(self, repo: ListRepository) -> None:
        repo.create(make_list())
        assert repo.delete_many([]) == 0
        assert repo.count() == 1

    def test_unknown_ids_are_ignored(self, repo: ListRepository) -> None:
        created = repo.create(make_list())
        assert repo.delete_many([created.id or 0, 999]) == 1
        assert repo.count() == 0

    def test_deletes_all_rows(self, repo: ListRepository) -> None:
        ids = [
            (repo.create(make_list(name=f"リスト{i}", list_url=f"{MEMO_URL}?v={i}")).id or 0)
            for i in range(5)
        ]
        assert repo.delete_many(ids) == 5
        assert repo.count() == 0

    def test_group_wide_delete_via_filter(self, repo: ListRepository) -> None:
        """グループで絞ってからまとめて削除する使い方を再現する。"""
        repo.create(make_list(group_name="開発"))
        repo.create(make_list(name="端末管理", list_url=DEVICES_URL, group_name="運用"))
        repo.create(make_list(name="総務メモ", list_url=MEMO_URL, group_name="運用"))

        targets = filter_lists(repo.list_all(), groups=["運用"])
        assert repo.delete_many([item.id or 0 for item in targets]) == 2
        assert [item.group_name for item in repo.list_all()] == ["開発"]


class TestDuplicateUrl:
    def test_create_duplicate_url_raises(self, repo: ListRepository) -> None:
        repo.create(make_list())
        with pytest.raises(DuplicateUrlError) as excinfo:
            repo.create(make_list(name="別のリスト"))
        assert excinfo.value.existing is not None
        assert excinfo.value.existing.name == "障害管理"
        assert repo.count() == 1

    def test_update_to_existing_url_raises(self, repo: ListRepository) -> None:
        first = repo.create(make_list())
        second = repo.create(make_list(name="端末管理", list_url=DEVICES_URL))
        with pytest.raises(DuplicateUrlError):
            repo.update(build_list(id=second.id, name="端末管理", list_url=first.list_url))


class TestFavorite:
    def test_set_favorite_on_and_off(self, repo: ListRepository) -> None:
        created = repo.create(make_list())
        assert created.favorite is False
        assert repo.set_favorite(created.id or 0, True) is True
        assert (repo.get_by_id(created.id or 0) or created).favorite is True
        repo.set_favorite(created.id or 0, False)
        assert (repo.get_by_id(created.id or 0) or created).favorite is False

    def test_set_favorite_missing_returns_false(self, repo: ListRepository) -> None:
        assert repo.set_favorite(999, True) is False


class TestOrderingAndAggregates:
    @pytest.fixture()
    def populated(self, repo: ListRepository) -> ListRepository:
        repo.create(make_list(name="B端末管理", list_url=DEVICES_URL, group_name="運用", tags=["端末"]))
        repo.create(make_list(name="A障害管理", list_url=ISSUES_URL, sort_order=1))
        repo.create(
            make_list(
                name="C総務メモ",
                list_url=MEMO_URL,
                group_name="",
                tags=["メモ", "端末"],
                environment="development",
                favorite=True,
            )
        )
        return repo

    def test_favorites_come_first(self, populated: ListRepository) -> None:
        names = [item.name for item in populated.list_all()]
        assert names[0] == "C総務メモ"

    def test_sort_order_then_name(self, populated: ListRepository) -> None:
        names = [item.name for item in populated.list_all()]
        assert names[1:] == ["B端末管理", "A障害管理"]

    def test_group_names_excludes_empty(self, populated: ListRepository) -> None:
        assert populated.group_names() == ["運用", "開発"]

    def test_tag_names_are_unique_and_sorted(self, populated: ListRepository) -> None:
        # 並び順はコードポイント順（日本語には言語固有の並べ替えを行わない）。
        assert populated.tag_names() == sorted({"障害", "本番", "端末", "メモ"})

    def test_environments(self, populated: ListRepository) -> None:
        assert populated.environments() == ["development", "production"]

    def test_group_by_puts_uncategorized_last(self, populated: ListRepository) -> None:
        grouped = group_by_group_name(populated.list_all())
        assert [name for name, _ in grouped] == ["運用", "開発", "未分類"]


class TestTagsJson:
    def test_tags_are_stored_as_json_array(self, repo: ListRepository) -> None:
        created = repo.create(make_list(tags=["障害", "本番"]))
        with connect(repo.db_path) as connection:
            row = connection.execute(
                "SELECT tags FROM lists WHERE id = ?", (created.id,)
            ).fetchone()
        assert row["tags"] == '["障害", "本番"]'
        assert tags_from_json(row["tags"]) == ["障害", "本番"]

    def test_empty_tags(self, repo: ListRepository) -> None:
        created = repo.create(make_list(tags=""))
        assert (repo.get_by_id(created.id or 0) or created).tags == []

    def test_broken_tags_json_falls_back_to_empty(self, repo: ListRepository) -> None:
        created = repo.create(make_list())
        with connect(repo.db_path) as connection, transaction(connection):
            connection.execute(
                "UPDATE lists SET tags = ? WHERE id = ?", ("これはJSONではない", created.id)
            )
        stored = repo.get_by_id(created.id or 0)
        assert stored is not None
        assert stored.tags == []


class TestJapaneseData:
    def test_japanese_round_trip(self, repo: ListRepository) -> None:
        created = repo.create(
            make_list(
                name="全社アンケート（２０２６年度）",
                site_name="総務部サイト",
                description="回答状況の確認用。改行\nも保持する。",
                tags=["アンケート", "総務"],
            )
        )
        stored = repo.get_by_id(created.id or 0)
        assert stored is not None
        assert stored.name == "全社アンケート（２０２６年度）"
        assert stored.site_name == "総務部サイト"
        assert "改行" in stored.description
        assert stored.tags == ["アンケート", "総務"]

    def test_search_matches_japanese_substring(self, repo: ListRepository) -> None:
        repo.create(make_list())
        items = repo.list_all()
        assert matches_query(items[0], "障害") is True
        assert matches_query(items[0], "端末") is False


class TestTransaction:
    def test_rollback_on_error(self, repo: ListRepository) -> None:
        repo.create(make_list())
        with pytest.raises(sqlite3.IntegrityError):
            with connect(repo.db_path) as connection, transaction(connection):
                connection.execute(
                    "UPDATE lists SET name = ? WHERE list_url = ?", ("変更後", ISSUES_URL)
                )
                # UNIQUE制約違反を起こして、直前の更新ごと巻き戻すことを確認する。
                connection.execute(
                    """
                    INSERT INTO lists (name, list_url, created_at, updated_at)
                    VALUES ('重複', ?, '2026-01-01', '2026-01-01')
                    """,
                    (ISSUES_URL,),
                )
        stored = repo.get_by_url(ISSUES_URL)
        assert stored is not None
        assert stored.name == "障害管理"
        assert repo.count() == 1

    def test_commit_persists_across_connections(self, repo: ListRepository) -> None:
        repo.create(make_list())
        assert ListRepository(repo.db_path).count() == 1


class TestValidationInBuildList:
    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            build_list(name="   ", list_url=ISSUES_URL)

    def test_invalid_url_raises(self) -> None:
        with pytest.raises(ValidationError):
            build_list(name="x", list_url="javascript:alert(1)")

    def test_too_long_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            build_list(name="あ" * 201, list_url=ISSUES_URL)

    def test_tags_are_deduplicated_in_input_order(self) -> None:
        item = build_list(name="x", list_url=ISSUES_URL, tags=" 本番 , 障害 ,本番, ")
        assert item.tags == ["本番", "障害"]

    def test_sort_order_defaults_to_zero(self) -> None:
        assert build_list(name="x", list_url=ISSUES_URL, sort_order="").sort_order == 0

    def test_sort_order_must_be_integer(self) -> None:
        with pytest.raises(ValidationError):
            build_list(name="x", list_url=ISSUES_URL, sort_order="いち")


class TestSaveImportItems:
    def test_creates_new_items(self, repo: ListRepository) -> None:
        summary = save_import_items(
            repo,
            [make_list(), make_list(name="端末管理", list_url=DEVICES_URL)],
        )
        assert (summary.created, summary.updated, summary.skipped) == (2, 0, 0)
        assert summary.errors == []
        assert repo.count() == 2

    def test_skip_policy_keeps_existing(self, repo: ListRepository) -> None:
        repo.create(make_list())
        summary = save_import_items(repo, [make_list(name="別名")], DUPLICATE_SKIP)
        assert (summary.created, summary.updated, summary.skipped) == (0, 0, 1)
        stored = repo.get_by_url(ISSUES_URL)
        assert stored is not None
        assert stored.name == "障害管理"

    def test_update_policy_overwrites_existing(self, repo: ListRepository) -> None:
        created = repo.create(make_list())
        summary = save_import_items(
            repo, [make_list(name="別名", group_name="運用")], DUPLICATE_UPDATE
        )
        assert (summary.created, summary.updated, summary.skipped) == (0, 1, 0)
        stored = repo.get_by_id(created.id or 0)
        assert stored is not None
        assert stored.name == "別名"
        assert stored.group_name == "運用"
        assert repo.count() == 1

    def test_error_policy_reports_and_keeps_existing(self, repo: ListRepository) -> None:
        repo.create(make_list())
        summary = save_import_items(repo, [make_list(name="別名")], DUPLICATE_ERROR)
        assert (summary.created, summary.updated, summary.skipped) == (0, 0, 0)
        assert len(summary.errors) == 1
        stored = repo.get_by_url(ISSUES_URL)
        assert stored is not None
        assert stored.name == "障害管理"

    def test_mixed_new_and_duplicate(self, repo: ListRepository) -> None:
        repo.create(make_list())
        summary = save_import_items(
            repo,
            [make_list(name="別名"), make_list(name="端末管理", list_url=DEVICES_URL)],
            DUPLICATE_SKIP,
        )
        assert (summary.created, summary.updated, summary.skipped) == (1, 0, 1)
        assert summary.saved == 1
        assert repo.count() == 2

    def test_exported_json_round_trip(self, repo: ListRepository) -> None:
        """エクスポートしたJSONを再インポートしても内容が保たれる。"""
        repo.create(make_list())
        payload = json.dumps(
            {
                "schemaVersion": 1,
                "exportedAt": "2026-07-27T15:30:00+09:00",
                "lists": [to_export_dict(item) for item in repo.list_all()],
            },
            ensure_ascii=False,
        )

        restored = ListRepository(repo.db_path.parent / "restored.sqlite3")
        restored.initialize()
        entries = parse_json_text(payload).valid_entries
        summary = save_import_items(
            restored,
            [
                build_list(
                    name=entry.name,
                    list_url=entry.list_url,
                    new_item_url=entry.new_item_url,
                    settings_url=entry.settings_url,
                    site_name=entry.site_name,
                    group_name=entry.group_name,
                    tags=entry.tags,
                    environment=entry.environment,
                    description=entry.description,
                    favorite=entry.favorite,
                    sort_order=entry.sort_order,
                )
                for entry in entries
            ],
        )
        assert summary.created == 1
        original = repo.list_all()[0]
        copied = restored.list_all()[0]
        assert (copied.name, copied.list_url, copied.tags, copied.environment) == (
            original.name,
            original.list_url,
            original.tags,
            original.environment,
        )


class TestFilters:
    @pytest.fixture()
    def items(self, repo: ListRepository) -> list[SharePointList]:
        repo.create(make_list())
        repo.create(
            make_list(
                name="端末管理",
                list_url=DEVICES_URL,
                group_name="運用",
                tags=["端末"],
                environment="staging",
                site_name="情シス",
                favorite=True,
            )
        )
        repo.create(
            make_list(
                name="総務メモ",
                list_url=MEMO_URL,
                group_name="",
                tags=[],
                environment="",
                site_name="総務部",
            )
        )
        return repo.list_all()

    def test_no_filters_returns_all(self, items: list[SharePointList]) -> None:
        assert len(filter_lists(items)) == 3

    def test_favorites_only(self, items: list[SharePointList]) -> None:
        result = filter_lists(items, favorites_only=True)
        assert [item.name for item in result] == ["端末管理"]

    def test_query_matches_site_name(self, items: list[SharePointList]) -> None:
        assert [item.name for item in filter_lists(items, query="総務")] == ["総務メモ"]

    def test_query_matches_tag(self, items: list[SharePointList]) -> None:
        # 「本番」はタグにしか存在しない語。
        assert [item.name for item in filter_lists(items, query="本番")] == ["障害管理"]

    def test_query_matches_url(self, items: list[SharePointList]) -> None:
        assert [item.name for item in filter_lists(items, query="Lists/Devices")] == ["端末管理"]

    def test_query_is_case_insensitive(self, items: list[SharePointList]) -> None:
        assert [item.name for item in filter_lists(items, query="lists/devices")] == ["端末管理"]

    def test_group_filter_includes_uncategorized(self, items: list[SharePointList]) -> None:
        result = filter_lists(items, groups=["未分類"])
        assert [item.name for item in result] == ["総務メモ"]

    def test_combined_filters(self, items: list[SharePointList]) -> None:
        result = filter_lists(
            items,
            query="端末",
            favorites_only=True,
            groups=["運用"],
            tags=["端末"],
            environments=["staging"],
        )
        assert [item.name for item in result] == ["端末管理"]

    def test_combined_filters_with_conflict_returns_empty(
        self, items: list[SharePointList]
    ) -> None:
        assert filter_lists(items, groups=["運用"], environments=["production"]) == []

"""タブ（space）のテスト."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from constants import DEFAULT_SPACE
from database import connect, initialize_database, transaction
from import_parser import parse_json_text
from models import ValidationError, build_list
from repositories import ListRepository, SpaceError

ISSUES_URL = "https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx"
DEVICES_URL = "https://example.sharepoint.com/sites/dev/Lists/Devices/AllItems.aspx"
FORM_URL = "https://forms.office.com/Pages/DesignPageV2.aspx?id=abc"


@pytest.fixture()
def repo(tmp_path: Path) -> ListRepository:
    repository = ListRepository(tmp_path / "test.sqlite3")
    repository.initialize()
    return repository


@pytest.fixture()
def populated(repo: ListRepository) -> ListRepository:
    repo.add_space("Forms")
    repo.create(build_list(name="障害管理", list_url=ISSUES_URL, group_name="開発", tags=["障害"]))
    repo.create(
        build_list(name="端末管理", list_url=DEVICES_URL, group_name="運用", environment="staging")
    )
    repo.create(
        build_list(
            name="申請フォーム",
            list_url=FORM_URL,
            space="Forms",
            group_name="人事",
            tags=["申請"],
            environment="production",
        )
    )
    return repo


class TestDefaults:
    def test_initialize_creates_default_space(self, repo: ListRepository) -> None:
        assert repo.spaces() == [DEFAULT_SPACE]

    def test_new_item_goes_to_default_space(self, repo: ListRepository) -> None:
        created = repo.create(build_list(name="障害管理", list_url=ISSUES_URL))
        assert created.space == DEFAULT_SPACE
        assert (repo.get_by_id(created.id or 0) or created).space == DEFAULT_SPACE

    def test_blank_space_falls_back_to_default(self) -> None:
        assert build_list(name="x", list_url=ISSUES_URL, space="   ").space == DEFAULT_SPACE

    def test_space_is_trimmed(self) -> None:
        assert build_list(name="x", list_url=ISSUES_URL, space="  Forms  ").space == "Forms"

    def test_too_long_space_raises(self) -> None:
        with pytest.raises(ValidationError):
            build_list(name="x", list_url=ISSUES_URL, space="あ" * 51)


class TestScoping:
    def test_list_all_filters_by_space(self, populated: ListRepository) -> None:
        assert [item.name for item in populated.list_all("Forms")] == ["申請フォーム"]
        assert len(populated.list_all(DEFAULT_SPACE)) == 2
        assert len(populated.list_all()) == 3

    def test_count_and_count_by_space(self, populated: ListRepository) -> None:
        assert populated.count() == 3
        assert populated.count("Forms") == 1
        assert populated.count_by_space() == {DEFAULT_SPACE: 2, "Forms": 1}

    def test_group_names_are_scoped(self, populated: ListRepository) -> None:
        assert populated.group_names("Forms") == ["人事"]
        assert populated.group_names(DEFAULT_SPACE) == ["運用", "開発"]

    def test_tag_names_are_scoped(self, populated: ListRepository) -> None:
        assert populated.tag_names("Forms") == ["申請"]
        assert populated.tag_names(DEFAULT_SPACE) == ["障害"]

    def test_environments_are_scoped(self, populated: ListRepository) -> None:
        assert populated.environments("Forms") == ["production"]
        assert populated.environments(DEFAULT_SPACE) == ["staging"]

    def test_url_is_unique_across_spaces(self, populated: ListRepository) -> None:
        """一覧URLはタブをまたいでも一意（同じものを二重管理しない）。"""
        from repositories import DuplicateUrlError

        with pytest.raises(DuplicateUrlError):
            populated.create(build_list(name="別タブの同じリスト", list_url=ISSUES_URL, space="Forms"))


class TestAddSpace:
    def test_add_and_order(self, repo: ListRepository) -> None:
        repo.add_space("Forms")
        repo.add_space("サイト")
        assert repo.spaces() == [DEFAULT_SPACE, "Forms", "サイト"]

    def test_add_existing_is_noop(self, repo: ListRepository) -> None:
        repo.add_space("Forms")
        repo.add_space("Forms")
        assert repo.spaces().count("Forms") == 1

    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_blank_name_raises(self, repo: ListRepository, name: str | None) -> None:
        with pytest.raises(SpaceError):
            repo.add_space(name)  # type: ignore[arg-type]


class TestRenameSpace:
    def test_rename_moves_items(self, populated: ListRepository) -> None:
        assert populated.rename_space("Forms", "フォーム") == 1
        assert "フォーム" in populated.spaces()
        assert "Forms" not in populated.spaces()
        assert [item.name for item in populated.list_all("フォーム")] == ["申請フォーム"]

    def test_rename_to_existing_raises(self, populated: ListRepository) -> None:
        with pytest.raises(SpaceError):
            populated.rename_space("Forms", DEFAULT_SPACE)

    def test_rename_to_same_name_is_noop(self, populated: ListRepository) -> None:
        assert populated.rename_space("Forms", "Forms") == 0

    def test_rename_to_blank_raises(self, populated: ListRepository) -> None:
        with pytest.raises(SpaceError):
            populated.rename_space("Forms", "  ")


class TestDeleteSpace:
    def test_delete_moves_items(self, populated: ListRepository) -> None:
        assert populated.delete_space("Forms", move_to=DEFAULT_SPACE) == 1
        assert populated.spaces() == [DEFAULT_SPACE]
        assert populated.count(DEFAULT_SPACE) == 3

    def test_delete_removes_items_when_no_destination(self, populated: ListRepository) -> None:
        assert populated.delete_space("Forms") == 1
        assert populated.count() == 2
        assert populated.spaces() == [DEFAULT_SPACE]

    def test_cannot_delete_last_space(self, repo: ListRepository) -> None:
        with pytest.raises(SpaceError):
            repo.delete_space(DEFAULT_SPACE)

    def test_unknown_space_raises(self, populated: ListRepository) -> None:
        with pytest.raises(SpaceError):
            populated.delete_space("存在しない")

    def test_unknown_destination_raises(self, populated: ListRepository) -> None:
        with pytest.raises(SpaceError):
            populated.delete_space("Forms", move_to="存在しない")


class TestMoveAndReorder:
    def test_move_to_space(self, populated: ListRepository) -> None:
        ids = [item.id or 0 for item in populated.list_all(DEFAULT_SPACE)]
        assert populated.move_to_space(ids, "Forms") == 2
        assert populated.count("Forms") == 3
        assert populated.count(DEFAULT_SPACE) == 0

    def test_move_to_unknown_space_raises(self, populated: ListRepository) -> None:
        with pytest.raises(SpaceError):
            populated.move_to_space([1], "存在しない")

    def test_move_empty_selection(self, populated: ListRepository) -> None:
        assert populated.move_to_space([], "Forms") == 0

    def test_reorder(self, populated: ListRepository) -> None:
        populated.reorder_spaces(["Forms", DEFAULT_SPACE])
        assert populated.spaces() == ["Forms", DEFAULT_SPACE]


class TestMigration:
    """タブ導入前のDBを開いても壊れないことを確認する。"""

    OLD_SCHEMA = """
    CREATE TABLE lists (
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
    """

    @pytest.fixture()
    def old_db(self, tmp_path: Path) -> Path:
        db_path = tmp_path / "old.sqlite3"
        connection = sqlite3.connect(db_path)
        connection.executescript(self.OLD_SCHEMA)
        connection.execute(
            """
            INSERT INTO lists (name, list_url, site_name, group_name, tags,
                               created_at, updated_at)
            VALUES ('既存の障害管理', ?, '開発部', '開発', '["障害"]', '2026-01-01', '2026-01-01')
            """,
            (ISSUES_URL,),
        )
        connection.commit()
        connection.close()
        return db_path

    def test_existing_rows_survive(self, old_db: Path) -> None:
        initialize_database(old_db)
        repository = ListRepository(old_db)
        items = repository.list_all()
        assert [item.name for item in items] == ["既存の障害管理"]
        assert items[0].space == DEFAULT_SPACE
        assert items[0].tags == ["障害"]
        assert items[0].group_name == "開発"

    def test_default_space_registered(self, old_db: Path) -> None:
        initialize_database(old_db)
        assert ListRepository(old_db).spaces() == [DEFAULT_SPACE]

    def test_initialize_is_idempotent(self, old_db: Path) -> None:
        initialize_database(old_db)
        initialize_database(old_db)
        repository = ListRepository(old_db)
        assert repository.count() == 1
        assert repository.spaces() == [DEFAULT_SPACE]

    def test_unknown_space_in_rows_is_registered(self, old_db: Path) -> None:
        """手動でタブ名を入れた行があれば、タブ一覧にも現れる（自己修復）。"""
        initialize_database(old_db)
        with connect(old_db) as connection, transaction(connection):
            connection.execute("UPDATE lists SET space = 'Forms'")
        initialize_database(old_db)
        assert ListRepository(old_db).spaces() == [DEFAULT_SPACE, "Forms"]


class TestImportParser:
    def test_space_key_is_read(self) -> None:
        payload = '{"name": "申請", "listUrl": "%s", "space": "Forms"}' % FORM_URL
        entry = parse_json_text(payload).entries[0]
        assert entry.space == "Forms"

    def test_tab_alias_is_read(self) -> None:
        payload = '{"name": "申請", "listUrl": "%s", "tab": "Forms"}' % FORM_URL
        assert parse_json_text(payload).entries[0].space == "Forms"

    def test_missing_space_is_blank(self) -> None:
        payload = '{"name": "申請", "listUrl": "%s"}' % FORM_URL
        assert parse_json_text(payload).entries[0].space == ""


class TestExportRoundTrip:
    def test_space_is_exported_and_restored(self, populated: ListRepository, tmp_path: Path) -> None:
        import json

        from models import to_export_dict

        payload = json.dumps(
            {"schemaVersion": 1, "lists": [to_export_dict(i) for i in populated.list_all()]},
            ensure_ascii=False,
        )
        entries = parse_json_text(payload).valid_entries
        assert {entry.space for entry in entries} == {DEFAULT_SPACE, "Forms"}

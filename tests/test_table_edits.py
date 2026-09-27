"""表ビューの編集差分（app.collect_table_updates）のテスト."""

from __future__ import annotations

from typing import Any

import pytest

from app import build_table_rows, collect_table_updates
from constants import DEFAULT_SPACE
from models import SharePointList, build_list

ISSUES_URL = "https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx"
DEVICES_URL = "https://example.sharepoint.com/sites/dev/Lists/Devices/AllItems.aspx"


def make_item(list_id: int, **overrides: Any) -> SharePointList:
    values: dict[str, Any] = {
        "id": list_id,
        "name": "障害管理",
        "list_url": ISSUES_URL,
        "settings_url": "https://example.sharepoint.com/sites/dev/_layouts/15/listedit.aspx",
        "new_item_url": "https://example.sharepoint.com/sites/dev/Lists/Issues/NewForm.aspx",
        "site_name": "開発部",
        "group_name": "開発",
        "tags": "障害, 本番",
        "environment": "production",
        "description": "障害の記録",
    }
    values.update(overrides)
    return build_list(**values)


@pytest.fixture()
def items() -> list[SharePointList]:
    return [
        make_item(1),
        make_item(2, name="端末管理", list_url=DEVICES_URL, group_name="運用", tags="端末"),
    ]


class TestNoChange:
    def test_untouched_rows_produce_nothing(self, items: list[SharePointList]) -> None:
        updates, errors = collect_table_updates(items, build_table_rows(items))
        assert updates == []
        assert errors == []

    def test_selection_checkbox_is_not_a_change(self, items: list[SharePointList]) -> None:
        rows = build_table_rows(items)
        rows[0]["選択"] = True
        updates, errors = collect_table_updates(items, rows)
        assert updates == []
        assert errors == []


class TestEdits:
    def test_group_change_is_detected(self, items: list[SharePointList]) -> None:
        rows = build_table_rows(items)
        rows[0]["グループ"] = "運用"
        updates, errors = collect_table_updates(items, rows)
        assert errors == []
        assert len(updates) == 1
        assert (updates[0].id, updates[0].group_name) == (1, "運用")

    def test_only_changed_rows_are_returned(self, items: list[SharePointList]) -> None:
        rows = build_table_rows(items)
        rows[1]["★"] = True
        updates, _ = collect_table_updates(items, rows)
        assert [item.id for item in updates] == [2]
        assert updates[0].favorite is True

    def test_tags_are_normalized(self, items: list[SharePointList]) -> None:
        rows = build_table_rows(items)
        rows[0]["タグ"] = " 本番 , 障害 ,本番, "
        updates, _ = collect_table_updates(items, rows)
        assert updates[0].tags == ["本番", "障害"]

    def test_environment_label_maps_back_to_value(self, items: list[SharePointList]) -> None:
        rows = build_table_rows(items)
        rows[0]["環境"] = "検証"
        updates, _ = collect_table_updates(items, rows)
        assert updates[0].environment == "staging"

    def test_environment_unset_maps_to_empty(self, items: list[SharePointList]) -> None:
        rows = build_table_rows(items)
        rows[0]["環境"] = "未設定"
        updates, _ = collect_table_updates(items, rows)
        assert updates[0].environment == ""

    def test_empty_group_is_allowed(self, items: list[SharePointList]) -> None:
        rows = build_table_rows(items)
        rows[0]["グループ"] = ""
        updates, _ = collect_table_updates(items, rows)
        assert updates[0].group_name == ""

    @pytest.mark.parametrize("value,expected", [(5, 5), ("7", 7), (3.0, 3), (None, 0), ("", 0)])
    def test_sort_order_coercion(
        self, items: list[SharePointList], value: Any, expected: int
    ) -> None:
        rows = build_table_rows(items)
        rows[0]["表示順"] = value
        updates, errors = collect_table_updates(items, rows)
        assert errors == []
        assert updates[0].sort_order == expected

    def test_nan_sort_order_becomes_zero(self, items: list[SharePointList]) -> None:
        rows = build_table_rows(items)
        rows[0]["表示順"] = float("nan")
        updates, errors = collect_table_updates(items, rows)
        assert errors == []
        assert updates[0].sort_order == 0


class TestSpaceColumn:
    def test_space_is_shown(self, items: list[SharePointList]) -> None:
        rows = build_table_rows(items)
        assert rows[0]["タブ"] == items[0].space

    def test_changing_space_moves_the_row(self, items: list[SharePointList]) -> None:
        rows = build_table_rows(items)
        rows[0]["タブ"] = "Forms"
        updates, errors = collect_table_updates(items, rows)
        assert errors == []
        assert [(u.id, u.space) for u in updates] == [(1, "Forms")]

    def test_blank_space_falls_back_to_default(self, items: list[SharePointList]) -> None:
        rows = build_table_rows(items)
        rows[0]["タブ"] = ""
        updates, _ = collect_table_updates(items, rows)
        assert updates[0].space == DEFAULT_SPACE


class TestPreservesHiddenFields:
    def test_url_description_and_new_item_url_are_kept(
        self, items: list[SharePointList]
    ) -> None:
        rows = build_table_rows(items)
        rows[0]["リスト名"] = "障害管理（改）"
        updates, _ = collect_table_updates(items, rows)
        updated = updates[0]
        assert updated.list_url == items[0].list_url
        assert updated.settings_url == items[0].settings_url
        assert updated.new_item_url == items[0].new_item_url
        assert updated.description == items[0].description


class TestRowMatching:
    def test_rows_are_matched_by_id_not_position(self, items: list[SharePointList]) -> None:
        """表を並べ替えても、ID で突き合わせるので取り違えない。"""
        rows = list(reversed(build_table_rows(items)))
        rows[0]["グループ"] = "法務"  # 並べ替え後の先頭は id=2
        updates, _ = collect_table_updates(items, rows)
        assert [(item.id, item.group_name) for item in updates] == [(2, "法務")]

    def test_unknown_id_is_ignored(self, items: list[SharePointList]) -> None:
        rows = build_table_rows(items)
        rows.append({**rows[0], "ID": 999, "グループ": "幽霊"})
        updates, errors = collect_table_updates(items, rows)
        assert updates == []
        assert errors == []


class TestValidation:
    def test_empty_name_is_reported_and_others_still_saved(
        self, items: list[SharePointList]
    ) -> None:
        rows = build_table_rows(items)
        rows[0]["リスト名"] = "   "
        rows[1]["グループ"] = "運用2"
        updates, errors = collect_table_updates(items, rows)
        assert [item.id for item in updates] == [2]
        assert len(errors) == 1
        assert "障害管理" in errors[0]

    def test_too_long_tag_is_reported(self, items: list[SharePointList]) -> None:
        rows = build_table_rows(items)
        rows[0]["タグ"] = "あ" * 51
        updates, errors = collect_table_updates(items, rows)
        assert updates == []
        assert len(errors) == 1

    def test_invalid_sort_order_is_reported(self, items: list[SharePointList]) -> None:
        rows = build_table_rows(items)
        rows[0]["表示順"] = "いち"
        updates, errors = collect_table_updates(items, rows)
        assert updates == []
        assert len(errors) == 1

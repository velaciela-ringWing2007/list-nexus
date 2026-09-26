"""import_parser のテスト."""

from __future__ import annotations

import json

import pytest

from import_parser import (
    SOURCE_HTML,
    SOURCE_JSON,
    SOURCE_MARKDOWN,
    SOURCE_TEXT,
    parse_import_text,
    parse_json_text,
)

ISSUES_URL = "https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx"
ISSUES_NEW_URL = "https://example.sharepoint.com/sites/dev/Lists/Issues/NewForm.aspx"
DEVICES_URL = "https://example.sharepoint.com/sites/dev/Lists/Devices/AllItems.aspx"


class TestJsonObject:
    def test_camel_case(self) -> None:
        text = json.dumps({"name": "障害管理", "listUrl": ISSUES_URL, "newItemUrl": ISSUES_NEW_URL})
        result = parse_import_text(text)
        assert result.errors == []
        assert len(result.entries) == 1
        entry = result.entries[0]
        assert entry.name == "障害管理"
        assert entry.list_url == ISSUES_URL
        assert entry.new_item_url == ISSUES_NEW_URL
        assert entry.source == SOURCE_JSON
        assert entry.is_valid

    def test_snake_case(self) -> None:
        text = json.dumps(
            {"name": "障害管理", "list_url": ISSUES_URL, "new_item_url": ISSUES_NEW_URL}
        )
        entry = parse_import_text(text).entries[0]
        assert entry.list_url == ISSUES_URL
        assert entry.new_item_url == ISSUES_NEW_URL

    def test_bookmarklet_output_ignores_extra_keys(self) -> None:
        text = json.dumps(
            {
                "name": "障害管理",
                "listUrl": ISSUES_URL,
                "sourceTitle": "障害管理 - Microsoft Lists",
                "capturedAt": "2026-07-27T12:00:00.000Z",
            }
        )
        entry = parse_import_text(text).entries[0]
        assert entry.name == "障害管理"
        assert entry.is_valid

    def test_data_without_list_url_is_invalid(self) -> None:
        """一覧URLが無いデータ（旧・新規作成URL取得Bookmarkletの出力など）は不正扱い。"""
        text = json.dumps(
            {"action": "newItem", "name": "障害管理", "newItemUrl": ISSUES_NEW_URL}
        )
        entry = parse_import_text(text).entries[0]
        # 画面では扱わないが、値自体は保持する（バックアップ互換のため）。
        assert entry.new_item_url == ISSUES_NEW_URL
        assert not entry.is_valid
        assert any("一覧URL" in error for error in entry.errors)

    def test_optional_fields(self) -> None:
        text = json.dumps(
            {
                "name": "障害管理",
                "listUrl": ISSUES_URL,
                "siteName": "開発部",
                "group": "開発",
                "tags": ["障害", "本番", "障害", " "],
                "environment": "production",
                "description": "障害の記録",
                "favorite": True,
                "sortOrder": 5,
            }
        )
        entry = parse_import_text(text).entries[0]
        assert entry.site_name == "開発部"
        assert entry.group_name == "開発"
        assert entry.tags == ["障害", "本番"]
        assert entry.environment == "production"
        assert entry.favorite is True
        assert entry.sort_order == 5

    def test_tags_as_comma_string(self) -> None:
        text = json.dumps({"name": "障害管理", "listUrl": ISSUES_URL, "tags": "障害, 本番 ,,障害"})
        assert parse_import_text(text).entries[0].tags == ["障害", "本番"]

    def test_unknown_environment_falls_back_to_empty(self) -> None:
        text = json.dumps({"name": "x", "listUrl": ISSUES_URL, "environment": "宇宙"})
        assert parse_import_text(text).entries[0].environment == ""

    def test_invalid_url_scheme_is_reported(self) -> None:
        text = json.dumps({"name": "悪意", "listUrl": "javascript:alert(1)"})
        entry = parse_import_text(text).entries[0]
        assert not entry.is_valid
        assert entry.errors


class TestJsonArray:
    def test_multiple_entries(self) -> None:
        text = json.dumps(
            [
                {"name": "障害管理", "listUrl": ISSUES_URL},
                {"name": "端末管理", "listUrl": DEVICES_URL},
            ]
        )
        result = parse_import_text(text)
        assert [entry.name for entry in result.entries] == ["障害管理", "端末管理"]
        assert all(entry.is_valid for entry in result.entries)

    def test_non_object_element_is_reported(self) -> None:
        text = json.dumps([{"name": "障害管理", "listUrl": ISSUES_URL}, "ゴミ"])
        result = parse_import_text(text)
        assert len(result.entries) == 1
        assert result.errors

    def test_empty_array(self) -> None:
        result = parse_import_text("[]")
        assert result.entries == []
        assert result.errors


class TestBackupFormat:
    def test_export_shape_is_accepted(self) -> None:
        text = json.dumps(
            {
                "schemaVersion": 1,
                "exportedAt": "2026-07-27T15:30:00+09:00",
                "lists": [
                    {"name": "障害管理", "listUrl": ISSUES_URL, "tags": ["障害"]},
                    {"name": "端末管理", "listUrl": DEVICES_URL},
                ],
            }
        )
        result = parse_json_text(text)
        assert result.errors == []
        assert len(result.entries) == 2
        assert result.entries[0].tags == ["障害"]

    def test_unknown_schema_version_warns_but_parses(self) -> None:
        text = json.dumps({"schemaVersion": 99, "lists": [{"name": "x", "listUrl": ISSUES_URL}]})
        result = parse_json_text(text)
        assert len(result.entries) == 1
        assert result.errors


class TestMarkdownLink:
    def test_single_link(self) -> None:
        result = parse_import_text(f"[障害管理]({ISSUES_URL})")
        assert len(result.entries) == 1
        entry = result.entries[0]
        assert entry.name == "障害管理"
        assert entry.list_url == ISSUES_URL
        assert entry.source == SOURCE_MARKDOWN

    def test_multiple_links(self) -> None:
        text = f"- [障害管理]({ISSUES_URL})\n- [端末管理]({DEVICES_URL})"
        result = parse_import_text(text)
        assert [entry.name for entry in result.entries] == ["障害管理", "端末管理"]

    def test_link_without_name_is_invalid(self) -> None:
        result = parse_import_text(f"[]({ISSUES_URL})")
        assert not result.entries[0].is_valid


class TestHtmlLink:
    def test_anchor_tag(self) -> None:
        text = f'<a href="{ISSUES_URL}">障害管理</a>'
        result = parse_import_text(text)
        entry = result.entries[0]
        assert entry.name == "障害管理"
        assert entry.list_url == ISSUES_URL
        assert entry.source == SOURCE_HTML

    def test_multiline_anchor_with_attributes(self) -> None:
        text = f'<a class="x" href="{ISSUES_URL}" target="_blank">\n  障害管理\n</a>'
        assert parse_import_text(text).entries[0].name == "障害管理"

    def test_html_entities_are_unescaped(self) -> None:
        text = f'<a href="{ISSUES_URL}&amp;view=1">障害 &amp; 対応</a>'
        entry = parse_import_text(text).entries[0]
        assert entry.name == "障害 & 対応"
        assert entry.list_url == f"{ISSUES_URL}&view=1"

    def test_nested_tags_in_anchor_text(self) -> None:
        text = f'<a href="{ISSUES_URL}"><span>障害管理</span></a>'
        assert parse_import_text(text).entries[0].name == "障害管理"


class TestNameAndUrl:
    def test_name_then_url(self) -> None:
        result = parse_import_text(f"障害管理\n{ISSUES_URL}")
        entry = result.entries[0]
        assert entry.name == "障害管理"
        assert entry.list_url == ISSUES_URL
        assert entry.source == SOURCE_TEXT

    def test_name_and_url_on_same_line(self) -> None:
        entry = parse_import_text(f"障害管理  {ISSUES_URL}").entries[0]
        assert entry.name == "障害管理"
        assert entry.list_url == ISSUES_URL

    def test_multiple_blocks(self) -> None:
        text = f"障害管理\n{ISSUES_URL}\n\n端末管理\n{DEVICES_URL}\n"
        result = parse_import_text(text)
        assert [(e.name, e.list_url) for e in result.entries] == [
            ("障害管理", ISSUES_URL),
            ("端末管理", DEVICES_URL),
        ]
        assert all(entry.is_valid for entry in result.entries)

    def test_url_only_needs_name(self) -> None:
        result = parse_import_text(ISSUES_URL)
        entry = result.entries[0]
        assert entry.list_url == ISSUES_URL
        assert entry.name == ""
        assert not entry.is_valid
        assert any("リスト名" in error for error in entry.errors)

    def test_trailing_punctuation_is_trimmed(self) -> None:
        entry = parse_import_text(f"障害管理\n{ISSUES_URL}。").entries[0]
        assert entry.list_url == ISSUES_URL


class TestErrors:
    @pytest.mark.parametrize("text", ["", "   ", "\n\n", None])
    def test_empty_input(self, text: str | None) -> None:
        result = parse_import_text(text)
        assert result.entries == []
        assert result.errors

    def test_broken_json(self) -> None:
        result = parse_import_text('{"name": "障害管理", "listUrl": ')
        assert result.entries == []
        assert any("JSON" in error for error in result.errors)

    def test_text_without_url(self) -> None:
        result = parse_import_text("障害管理\n端末管理")
        assert result.entries == []
        assert result.errors

    def test_json_scalar_is_rejected(self) -> None:
        result = parse_json_text("123")
        assert result.entries == []
        assert result.errors

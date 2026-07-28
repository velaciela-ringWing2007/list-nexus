"""url_utils のテスト."""

from __future__ import annotations

import pytest

from url_utils import (
    UrlValidationError,
    is_valid_url,
    normalize_url,
    strip_query_and_fragment,
    suggest_new_item_url,
    validate_optional_url,
    validate_url,
)

BASE = "https://example.sharepoint.com/sites/dev/Lists/Issues"


class TestSuggestNewItemUrl:
    def test_all_items_becomes_new_form(self) -> None:
        assert suggest_new_item_url(f"{BASE}/AllItems.aspx") == f"{BASE}/NewForm.aspx"

    def test_my_items_becomes_new_form(self) -> None:
        assert suggest_new_item_url(f"{BASE}/MyItems.aspx") == f"{BASE}/NewForm.aspx"

    def test_by_author_becomes_new_form(self) -> None:
        assert suggest_new_item_url(f"{BASE}/ByAuthor.aspx") == f"{BASE}/NewForm.aspx"

    def test_query_string_is_removed(self) -> None:
        url = f"{BASE}/AllItems.aspx?viewid=abc-123&env=WebViewList"
        assert suggest_new_item_url(url) == f"{BASE}/NewForm.aspx"

    def test_fragment_is_removed(self) -> None:
        url = f"{BASE}/AllItems.aspx#section"
        assert suggest_new_item_url(url) == f"{BASE}/NewForm.aspx"

    def test_case_insensitive_page_name(self) -> None:
        assert suggest_new_item_url(f"{BASE}/allitems.ASPX") == f"{BASE}/NewForm.aspx"

    def test_japanese_path_is_preserved(self) -> None:
        url = "https://example.sharepoint.com/sites/開発/Lists/障害/AllItems.aspx"
        expected = "https://example.sharepoint.com/sites/開発/Lists/障害/NewForm.aspx"
        assert suggest_new_item_url(url) == expected

    def test_unsupported_page_returns_empty(self) -> None:
        assert suggest_new_item_url(f"{BASE}/Dashboard.aspx") == ""

    def test_url_without_path_returns_empty(self) -> None:
        assert suggest_new_item_url("https://example.sharepoint.com") == ""

    @pytest.mark.parametrize(
        "value",
        ["", "   ", None, "not a url", "javascript:alert(1)", "ftp://example.com/AllItems.aspx"],
    )
    def test_invalid_url_returns_empty(self, value: str | None) -> None:
        assert suggest_new_item_url(value) == ""


class TestValidateUrl:
    @pytest.mark.parametrize(
        "url",
        [
            f"{BASE}/AllItems.aspx",
            "http://example.com/",
            "  https://example.com/path?q=1  ",
        ],
    )
    def test_accepts_http_and_https(self, url: str) -> None:
        assert validate_url(url) == url.strip()

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "JavaScript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "file:///C:/temp/a.txt",
            "ftp://example.com/",
            "example.com/AllItems.aspx",
            "https://",
            "",
            "   ",
            None,
        ],
    )
    def test_rejects_unsupported_values(self, url: str | None) -> None:
        with pytest.raises(UrlValidationError):
            validate_url(url)

    def test_rejects_newline(self) -> None:
        with pytest.raises(UrlValidationError):
            validate_url("https://example.com/a\nhttps://example.com/b")

    def test_rejects_too_long_url(self) -> None:
        with pytest.raises(UrlValidationError):
            validate_url("https://example.com/" + "a" * 3000)

    def test_is_valid_url_does_not_raise(self) -> None:
        assert is_valid_url(f"{BASE}/AllItems.aspx") is True
        assert is_valid_url("javascript:alert(1)") is False

    def test_optional_url_allows_empty(self) -> None:
        assert validate_optional_url("") == ""
        assert validate_optional_url("   ") == ""
        assert validate_optional_url(None) == ""

    def test_optional_url_still_validates_value(self) -> None:
        with pytest.raises(UrlValidationError):
            validate_optional_url("javascript:alert(1)")


class TestStripQueryAndFragment:
    def test_removes_query_and_fragment(self) -> None:
        url = f"{BASE}/AllItems.aspx?viewid=1#top"
        assert strip_query_and_fragment(url) == f"{BASE}/AllItems.aspx"

    def test_keeps_plain_url(self) -> None:
        assert strip_query_and_fragment(f"{BASE}/AllItems.aspx") == f"{BASE}/AllItems.aspx"

    def test_non_url_text_is_returned_trimmed(self) -> None:
        assert strip_query_and_fragment("  障害管理  ") == "障害管理"

    def test_empty_returns_empty(self) -> None:
        assert strip_query_and_fragment(None) == ""


def test_normalize_url_trims_whitespace() -> None:
    assert normalize_url("  https://example.com/  ") == "https://example.com/"
    assert normalize_url(None) == ""

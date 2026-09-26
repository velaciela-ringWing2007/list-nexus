"""url_utils のテスト."""

from __future__ import annotations

import pytest

from url_utils import (
    UrlValidationError,
    normalize_url,
    validate_optional_url,
    validate_url,
)

BASE = "https://example.sharepoint.com/sites/dev/Lists/Issues"


class TestValidateUrl:
    @pytest.mark.parametrize(
        "url",
        [
            f"{BASE}/AllItems.aspx",
            f"{BASE}/AllItems.aspx?viewid=abc-123",
            "https://example.sharepoint.com/sites/開発/Lists/障害/AllItems.aspx",
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

    def test_rejects_tab(self) -> None:
        with pytest.raises(UrlValidationError):
            validate_url("https://example.com/a\tb")

    def test_rejects_too_long_url(self) -> None:
        with pytest.raises(UrlValidationError):
            validate_url("https://example.com/" + "a" * 3000)

    def test_error_message_uses_field_label(self) -> None:
        with pytest.raises(UrlValidationError, match="一覧URL"):
            validate_url("", field_label="一覧URL")


class TestValidateOptionalUrl:
    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_allows_empty(self, value: str | None) -> None:
        assert validate_optional_url(value) == ""

    def test_still_validates_value(self) -> None:
        with pytest.raises(UrlValidationError):
            validate_optional_url("javascript:alert(1)")

    def test_returns_trimmed_url(self) -> None:
        assert validate_optional_url(f"  {BASE}/AllItems.aspx  ") == f"{BASE}/AllItems.aspx"


def test_normalize_url_trims_whitespace() -> None:
    assert normalize_url("  https://example.com/  ") == "https://example.com/"
    assert normalize_url(None) == ""

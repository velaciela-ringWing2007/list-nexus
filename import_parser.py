"""貼り付けテキストとバックアップJSONの解析.

解析結果は必ずプレビューを経由してユーザーが確定するため、
ここでは「解析できた内容」と「問題点」を返すだけで保存は行わない。
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from constants import SCHEMA_VERSION
from models import (
    ValidationError,
    normalize_environment,
    normalize_sort_order,
    normalize_tags,
)
from url_utils import UrlValidationError, normalize_url, validate_url

# 解析元の形式（プレビューでの表示用）
SOURCE_JSON = "JSON"
SOURCE_MARKDOWN = "Markdownリンク"
SOURCE_HTML = "HTMLリンク"
SOURCE_TEXT = "名前とURL"

_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(\s*(\S+?)\s*\)")
_HTML_ANCHOR_RE = re.compile(
    r"<a\b[^>]*\bhref\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# JSONのキー名ゆれ（camelCase / snake_case / 別名）を吸収する対応表。
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "listName", "list_name", "title", "displayName", "display_name"),
    "list_url": ("listUrl", "list_url", "url", "listURL", "viewUrl", "view_url"),
    "new_item_url": ("newItemUrl", "new_item_url", "newUrl", "new_url", "newFormUrl"),
    "settings_url": ("settingsUrl", "settings_url", "settingUrl", "setting_url"),
    "site_name": ("siteName", "site_name", "site"),
    "group_name": ("group", "groupName", "group_name"),
    "tags": ("tags", "tag"),
    "environment": ("environment", "env"),
    "description": ("description", "memo", "note", "comment"),
    "favorite": ("favorite", "isFavorite", "is_favorite", "favourite"),
    "sort_order": ("sortOrder", "sort_order", "order"),
}


@dataclass(slots=True)
class ParsedEntry:
    """解析できた1件分の候補データ."""

    name: str = ""
    list_url: str = ""
    new_item_url: str = ""
    settings_url: str = ""
    site_name: str = ""
    group_name: str = ""
    tags: list[str] = field(default_factory=list)
    environment: str = ""
    description: str = ""
    favorite: bool = False
    sort_order: int = 0
    source: str = SOURCE_TEXT
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass(slots=True)
class ParseResult:
    """解析結果全体."""

    entries: list[ParsedEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_entries(self) -> bool:
        return bool(self.entries)

    @property
    def valid_entries(self) -> list[ParsedEntry]:
        return [entry for entry in self.entries if entry.is_valid]


# ----------------------------------------------------------------------
# 共通ヘルパー
# ----------------------------------------------------------------------
def _pick(payload: dict[str, Any], canonical: str) -> Any:
    """別名を考慮して値を取り出す。見つからなければ None。"""
    for key in _FIELD_ALIASES[canonical]:
        if key in payload and payload[key] is not None:
            return payload[key]
    # 大文字小文字だけが異なるキーにも対応する。
    lowered = {str(key).lower(): value for key, value in payload.items()}
    for key in _FIELD_ALIASES[canonical]:
        value = lowered.get(key.lower())
        if value is not None:
            return value
    return None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    return str(value).strip()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "yes", "1", "on"}


def _clean_link_text(raw: str) -> str:
    """HTMLリンクのテキストからタグを除去し、実体参照を戻す。"""
    without_tags = _HTML_TAG_RE.sub("", raw)
    return html.unescape(without_tags).strip()


def validate_entry(entry: ParsedEntry) -> ParsedEntry:
    """必須項目とURL形式を検証し、errors を設定した同じインスタンスを返す。"""
    errors: list[str] = []

    if not entry.name.strip():
        errors.append("リスト名が取得できませんでした。入力してください。")

    if not entry.list_url.strip():
        errors.append("一覧URLが取得できませんでした。入力してください。")
    else:
        try:
            entry.list_url = validate_url(entry.list_url, field_label="一覧URL")
        except UrlValidationError as exc:
            errors.append(str(exc))

    for attr, label in (("new_item_url", "新規作成URL"), ("settings_url", "設定URL")):
        value = getattr(entry, attr).strip()
        if not value:
            setattr(entry, attr, "")
            continue
        try:
            setattr(entry, attr, validate_url(value, field_label=label))
        except UrlValidationError as exc:
            errors.append(str(exc))

    try:
        entry.tags = normalize_tags(entry.tags)
    except ValidationError as exc:
        errors.append(str(exc))

    entry.errors = errors
    return entry


# ----------------------------------------------------------------------
# JSON解析
# ----------------------------------------------------------------------
def entry_from_mapping(payload: dict[str, Any]) -> ParsedEntry:
    """辞書から ParsedEntry を作る（camelCase / snake_case 両対応）。"""
    entry = ParsedEntry(source=SOURCE_JSON)
    entry.name = _as_text(_pick(payload, "name"))
    entry.list_url = normalize_url(_as_text(_pick(payload, "list_url")))
    entry.new_item_url = normalize_url(_as_text(_pick(payload, "new_item_url")))
    entry.settings_url = normalize_url(_as_text(_pick(payload, "settings_url")))
    entry.site_name = _as_text(_pick(payload, "site_name"))
    entry.group_name = _as_text(_pick(payload, "group_name"))
    entry.environment = normalize_environment(_as_text(_pick(payload, "environment")))
    entry.description = _as_text(_pick(payload, "description"))

    favorite = _pick(payload, "favorite")
    entry.favorite = _as_bool(favorite) if favorite is not None else False

    sort_order = _pick(payload, "sort_order")
    try:
        entry.sort_order = normalize_sort_order(sort_order)
    except ValidationError:
        entry.sort_order = 0

    raw_tags = _pick(payload, "tags")
    if isinstance(raw_tags, str):
        entry.tags = [tag for tag in (part.strip() for part in raw_tags.split(",")) if tag]
    elif isinstance(raw_tags, Iterable) and not isinstance(raw_tags, (bytes, dict)):
        entry.tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()]

    validate_entry(entry)

    # 新規作成ページ取得Bookmarkletの出力には一覧URLが含まれない。
    # 何が足りないのかがプレビューで分かるように補足する。
    action = _as_text(payload.get("action")) or _as_text(payload.get("Action"))
    if action.lower() == "newitem" and not entry.list_url and entry.new_item_url:
        entry.errors.append(
            "新規作成URLのみのデータです。対応する一覧URLを入力してください。"
        )
    return entry


def _parse_json_payload(payload: Any) -> ParseResult:
    result = ParseResult()

    if isinstance(payload, dict):
        # エクスポート形式（{"schemaVersion": 1, "lists": [...]}）にも対応する。
        if isinstance(payload.get("lists"), list):
            version = payload.get("schemaVersion")
            if version is not None and version != SCHEMA_VERSION:
                result.errors.append(
                    f"未対応のschemaVersionです（想定: {SCHEMA_VERSION} / 実際: {version}）。"
                    "内容を確認してください。"
                )
            items: list[Any] = payload["lists"]
        else:
            items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        result.errors.append("JSONの形式に対応していません。オブジェクトか配列を貼り付けてください。")
        return result

    if not items:
        result.errors.append("JSONにデータが含まれていません。")
        return result

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            result.errors.append(f"{index}件目がオブジェクトではないため読み飛ばしました。")
            continue
        result.entries.append(entry_from_mapping(item))

    return result


def parse_json_text(text: str) -> ParseResult:
    """JSON文字列を解析する。JSONとして読めない場合はエラーを返す。"""
    result = ParseResult()
    stripped = text.strip()
    if not stripped:
        result.errors.append("入力が空です。")
        return result
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        result.errors.append(f"JSONを解析できませんでした（{exc.lineno}行目付近）。")
        return result
    return _parse_json_payload(payload)


# ----------------------------------------------------------------------
# テキスト解析
# ----------------------------------------------------------------------
def _entry_from_link(name: str, url: str, source: str) -> ParsedEntry:
    entry = ParsedEntry(name=name.strip(), list_url=normalize_url(url), source=source)
    return validate_entry(entry)


def _parse_plain_text(text: str) -> ParseResult:
    """Markdown / HTML / 名前+URL / URLのみ を行単位で解析する。"""
    result = ParseResult()
    pending_name = ""

    for anchor_url, anchor_text in _HTML_ANCHOR_RE.findall(text):
        result.entries.append(
            _entry_from_link(_clean_link_text(anchor_text), html.unescape(anchor_url), SOURCE_HTML)
        )
    remaining = _HTML_ANCHOR_RE.sub("\n", text) if result.entries else text

    for raw_line in remaining.splitlines():
        line = raw_line.strip()
        if not line:
            pending_name = ""
            continue

        markdown_links = _MARKDOWN_LINK_RE.findall(line)
        if markdown_links:
            for link_text, link_url in markdown_links:
                result.entries.append(
                    _entry_from_link(_clean_link_text(link_text), link_url, SOURCE_MARKDOWN)
                )
            pending_name = ""
            continue

        url_match = _URL_RE.search(line)
        if url_match:
            url = url_match.group(0).rstrip(".,;)]>。、")
            prefix = line[: url_match.start()].strip(" \t-–—:：|")
            name = prefix or pending_name
            result.entries.append(_entry_from_link(name, url, SOURCE_TEXT))
            pending_name = ""
            continue

        # URLを含まない行は、直後に来るURLの名前候補として保持する。
        pending_name = line

    if not result.entries:
        result.errors.append(
            "URLを見つけられませんでした。JSON、Markdownリンク、"
            "「名前とURL」のいずれかの形式で貼り付けてください。"
        )
    return result


def parse_import_text(text: str | None) -> ParseResult:
    """貼り付けテキストを形式自動判定で解析する。"""
    result = ParseResult()
    stripped = (text or "").strip()
    if not stripped:
        result.errors.append("入力が空です。")
        return result

    if stripped[0] == "{":
        return parse_json_text(stripped)

    if stripped[0] == "[":
        # JSON配列とMarkdownリンクはどちらも "[" で始まるため、順に試す。
        json_result = parse_json_text(stripped)
        if json_result.has_entries:
            return json_result
        text_result = _parse_plain_text(stripped)
        if text_result.has_entries:
            return text_result
        return json_result

    return _parse_plain_text(stripped)

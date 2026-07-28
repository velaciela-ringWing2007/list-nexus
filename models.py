"""データモデルと、SQLite行との相互変換."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from constants import (
    ENVIRONMENT_VALUES,
    MAX_NAME_LENGTH,
    MAX_TAG_LENGTH,
)
from url_utils import UrlValidationError, validate_optional_url, validate_url


class ValidationError(ValueError):
    """入力値が業務要件を満たさない場合に送出する例外."""


@dataclass(slots=True)
class SharePointList:
    """1件のSharePoint Listリンク情報."""

    id: int | None
    name: str
    list_url: str
    new_item_url: str = ""
    settings_url: str = ""
    site_name: str = ""
    group_name: str = ""
    tags: list[str] = field(default_factory=list)
    environment: str = ""
    description: str = ""
    favorite: bool = False
    sort_order: int = 0
    open_count: int = 0
    created_at: str = ""
    updated_at: str = ""


def now_iso() -> str:
    """ローカル時刻（タイムゾーン付き）のISO 8601文字列を返す。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def tags_to_json(tags: Iterable[str]) -> str:
    """タグのリストをDB保存用のJSON配列文字列へ変換する。"""
    return json.dumps(list(tags), ensure_ascii=False)


def tags_from_json(raw: str | None) -> list[str]:
    """DBのJSON配列文字列をタグのリストへ変換する。

    壊れた値が入っていても画面を落とさないよう、空リストへフォールバックする。
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(tag) for tag in parsed if str(tag).strip()]


def row_to_list(row: sqlite3.Row) -> SharePointList:
    """SQLiteの行をモデルへ変換する。"""
    return SharePointList(
        id=row["id"],
        name=row["name"],
        list_url=row["list_url"],
        new_item_url=row["new_item_url"] or "",
        settings_url=row["settings_url"] or "",
        site_name=row["site_name"] or "",
        group_name=row["group_name"] or "",
        tags=tags_from_json(row["tags"]),
        environment=row["environment"] or "",
        description=row["description"] or "",
        favorite=bool(row["favorite"]),
        sort_order=int(row["sort_order"]),
        open_count=int(row["open_count"]),
        created_at=row["created_at"] or "",
        updated_at=row["updated_at"] or "",
    )


def list_to_params(item: SharePointList) -> dict[str, Any]:
    """モデルをSQLのバインドパラメータへ変換する。"""
    return {
        "name": item.name,
        "list_url": item.list_url,
        "new_item_url": item.new_item_url,
        "settings_url": item.settings_url,
        "site_name": item.site_name,
        "group_name": item.group_name,
        "tags": tags_to_json(item.tags),
        "environment": item.environment,
        "description": item.description,
        "favorite": 1 if item.favorite else 0,
        "sort_order": item.sort_order,
        "open_count": item.open_count,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def normalize_name(raw: str | None) -> str:
    """リスト名を検証して正規化する。"""
    name = (raw or "").strip()
    if not name:
        raise ValidationError("リスト名を入力してください。")
    if len(name) > MAX_NAME_LENGTH:
        raise ValidationError(
            f"リスト名が長すぎます。{MAX_NAME_LENGTH}文字以内で入力してください。"
        )
    return name


def normalize_tags(raw: str | Iterable[str] | None) -> list[str]:
    """カンマ区切り文字列またはリストからタグのリストを作る。

    前後空白の除去、空タグの除去、重複除去を行い、入力順を維持する。
    """
    if raw is None:
        candidates: list[str] = []
    elif isinstance(raw, str):
        candidates = raw.replace("、", ",").split(",")
    else:
        candidates = [str(tag) for tag in raw]

    tags: list[str] = []
    for candidate in candidates:
        tag = str(candidate).strip()
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise ValidationError(
                f"タグ「{tag[:20]}…」が長すぎます。{MAX_TAG_LENGTH}文字以内で入力してください。"
            )
        if tag not in tags:
            tags.append(tag)
    return tags


def normalize_sort_order(raw: Any) -> int:
    """表示順を整数へ変換する。未入力は0とする。"""
    if raw is None or raw == "":
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError("表示順は整数で入力してください。") from exc


def normalize_environment(raw: str | None) -> str:
    """環境の内部値を正規化する。未知の値は空文字（未設定）とする。"""
    value = (raw or "").strip().lower()
    if value not in ENVIRONMENT_VALUES:
        return ""
    return value


def build_list(
    *,
    id: int | None = None,
    name: str | None,
    list_url: str | None,
    new_item_url: str | None = "",
    settings_url: str | None = "",
    site_name: str | None = "",
    group_name: str | None = "",
    tags: str | Iterable[str] | None = None,
    environment: str | None = "",
    description: str | None = "",
    favorite: bool = False,
    sort_order: Any = 0,
    open_count: int = 0,
) -> SharePointList:
    """入力値を検証・正規化して SharePointList を組み立てる。

    検証に失敗した場合は ValidationError を送出する。
    """
    try:
        validated_list_url = validate_url(list_url, field_label="一覧URL")
        validated_new_item_url = validate_optional_url(new_item_url, field_label="新規作成URL")
        validated_settings_url = validate_optional_url(settings_url, field_label="設定URL")
    except UrlValidationError as exc:
        raise ValidationError(str(exc)) from exc

    return SharePointList(
        id=id,
        name=normalize_name(name),
        list_url=validated_list_url,
        new_item_url=validated_new_item_url,
        settings_url=validated_settings_url,
        site_name=(site_name or "").strip(),
        group_name=(group_name or "").strip(),
        tags=normalize_tags(tags),
        environment=normalize_environment(environment),
        description=(description or "").strip(),
        favorite=bool(favorite),
        sort_order=normalize_sort_order(sort_order),
        open_count=int(open_count or 0),
    )

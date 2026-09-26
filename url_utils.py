"""URLの検証.

本アプリはSharePointのリンクを管理するだけで、アイテムの新規作成は扱わない。
そのため新規作成URL（NewForm.aspx）の候補生成は行わない。
"""

from __future__ import annotations

from urllib.parse import urlsplit

from constants import ALLOWED_URL_SCHEMES, MAX_URL_LENGTH


class UrlValidationError(ValueError):
    """URLが業務要件を満たさない場合に送出する例外."""


def normalize_url(raw: str | None) -> str:
    """前後の空白を除去した文字列を返す。None は空文字にする。"""
    if raw is None:
        return ""
    return str(raw).strip()


def validate_url(raw: str | None, *, field_label: str = "URL") -> str:
    """URLを検証して正規化した文字列を返す。

    - 前後の空白を除去する
    - http / https のみ許可する
    - javascript: と data: を拒否する
    - 改行を含むURLを拒否する
    """
    url = normalize_url(raw)
    if not url:
        raise UrlValidationError(f"{field_label}が空です。")

    if any(ch in url for ch in "\r\n\t"):
        raise UrlValidationError(f"{field_label}に改行や制御文字を含めることはできません。")

    if len(url) > MAX_URL_LENGTH:
        raise UrlValidationError(
            f"{field_label}が長すぎます。{MAX_URL_LENGTH}文字以内で入力してください。"
        )

    try:
        parts = urlsplit(url)
    except ValueError as exc:  # 例: 不正なIPv6リテラル
        raise UrlValidationError(f"{field_label}の形式が正しくありません。") from exc

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_URL_SCHEMES:
        raise UrlValidationError(
            f"{field_label}は http:// または https:// で始まる必要があります。"
        )
    if not parts.netloc:
        raise UrlValidationError(f"{field_label}にホスト名が含まれていません。")

    return url


def validate_optional_url(raw: str | None, *, field_label: str = "URL") -> str:
    """任意入力のURLを検証する。空文字の場合は空文字を返す。"""
    url = normalize_url(raw)
    if not url:
        return ""
    return validate_url(url, field_label=field_label)

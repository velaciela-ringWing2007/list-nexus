"""URLの検証と、SharePoint URLの候補生成を行うユーティリティ.

ここで生成したURLは常に「候補」であり、確定値として扱わない。
Power Appsカスタムフォームや独自ビューでは構成が異なるため、
呼び出し側は必ずユーザーが編集できる形で提示すること。
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from constants import ALLOWED_URL_SCHEMES, MAX_URL_LENGTH


class UrlValidationError(ValueError):
    """URLが業務要件を満たさない場合に送出する例外."""


# 一覧系ビューページとして扱うファイル名（小文字で比較する）。
KNOWN_VIEW_PAGES: frozenset[str] = frozenset(
    {
        "allitems.aspx",
        "myitems.aspx",
        "byauthor.aspx",
        "recent.aspx",
    }
)

NEW_FORM_PAGE: str = "NewForm.aspx"


def normalize_url(raw: str | None) -> str:
    """前後の空白を除去した文字列を返す。None は空文字にする。"""
    if raw is None:
        return ""
    return str(raw).strip()


def is_valid_url(raw: str | None) -> bool:
    """URLとして受け入れ可能かどうかを返す（例外を送出しない版）。"""
    try:
        validate_url(raw)
    except UrlValidationError:
        return False
    return True


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


def strip_query_and_fragment(raw: str | None) -> str:
    """クエリ文字列とフラグメントを除去したURLを返す。

    解析できない文字列は、前後の空白だけを除去して返す。
    """
    url = normalize_url(raw)
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.scheme or not parts.netloc:
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def suggest_new_item_url(list_url: str | None) -> str:
    """一覧URLから新規作成URL（NewForm.aspx）の候補を生成する。

    生成できない場合は空文字を返す。結果は候補にすぎないため、
    呼び出し側は必ず編集可能な形でユーザーへ提示すること。
    """
    url = normalize_url(list_url)
    if not url:
        return ""

    try:
        validate_url(url)
    except UrlValidationError:
        return ""

    parts = urlsplit(url)
    path = parts.path
    if not path:
        return ""

    head, separator, last_segment = path.rpartition("/")
    if not separator:
        return ""
    if last_segment.lower() not in KNOWN_VIEW_PAGES:
        return ""

    new_path = f"{head}/{NEW_FORM_PAGE}"
    # クエリ文字列とフラグメントは原則除去する。
    return urlunsplit((parts.scheme, parts.netloc, new_path, "", ""))

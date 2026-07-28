"""アプリケーション全体で共有する定数."""

from __future__ import annotations

from pathlib import Path
from typing import Final

APP_NAME: Final[str] = "LIST NEXUS"
APP_ICON: Final[str] = "⚡"

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent
DATA_DIR: Final[Path] = PROJECT_ROOT / "data"
DATABASE_PATH: Final[Path] = DATA_DIR / "list_nexus.sqlite3"

# エクスポートJSONのスキーマ版数。形式を変えるときに増やす。
SCHEMA_VERSION: Final[int] = 1

UNCATEGORIZED_GROUP: Final[str] = "未分類"

# environment カラムに保存する値と、画面表示に使う日本語ラベル。
# 未設定（空文字）も許可する。
ENVIRONMENT_LABELS: Final[dict[str, str]] = {
    "": "未設定",
    "production": "本番",
    "staging": "検証",
    "development": "開発",
    "test": "テスト",
    "personal": "個人",
    "other": "その他",
}
ENVIRONMENT_VALUES: Final[tuple[str, ...]] = tuple(ENVIRONMENT_LABELS)

# 強調表示する環境（本番は目立たせる）。
HIGHLIGHT_ENVIRONMENTS: Final[frozenset[str]] = frozenset({"production"})

MAX_NAME_LENGTH: Final[int] = 200
MAX_TAG_LENGTH: Final[int] = 50
MAX_URL_LENGTH: Final[int] = 2000

ALLOWED_URL_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})

# JSONインポート時の重複解決方針。
DUPLICATE_SKIP: Final[str] = "skip"
DUPLICATE_UPDATE: Final[str] = "update"
DUPLICATE_ERROR: Final[str] = "error"

DUPLICATE_POLICY_LABELS: Final[dict[str, str]] = {
    DUPLICATE_SKIP: "スキップ",
    DUPLICATE_UPDATE: "既存を更新",
    DUPLICATE_ERROR: "エラーとして扱う",
}


def environment_label(value: str) -> str:
    """環境の内部値を日本語ラベルへ変換する。未知の値はそのまま返す。"""
    return ENVIRONMENT_LABELS.get(value, value)

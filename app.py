"""LIST NEXUS - SharePoint Listリンクのローカルランチャー（Streamlit UI）.

UIはこのモジュールに閉じ込め、SQLやテキスト解析は
repositories / import_parser / url_utils に委譲する。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Iterable

import streamlit as st

from constants import (
    APP_ICON,
    APP_NAME,
    DATABASE_PATH,
    DUPLICATE_ERROR,
    DUPLICATE_POLICY_LABELS,
    DUPLICATE_SKIP,
    DUPLICATE_UPDATE,
    ENVIRONMENT_VALUES,
    SCHEMA_VERSION,
    UNCATEGORIZED_GROUP,
    environment_label,
)
from database import DatabaseError
from import_parser import ParsedEntry, parse_import_text, parse_json_text
from models import SharePointList, ValidationError, build_list, now_iso, to_export_dict
from repositories import (
    DuplicateUrlError,
    ListRepository,
    filter_lists,
    group_by_group_name,
    save_import_items,
)
from styles import (
    apply_styles,
    chip,
    environment_chip,
    render_brand,
    render_description,
    render_meta_row,
    render_note,
    render_section_heading,
    render_title,
)
from url_utils import suggest_new_item_url

logger = logging.getLogger("list_nexus")

TILE_COLUMNS = 3

# 登録・編集ダイアログのウィジェットキー
FORM_KEYS: dict[str, Any] = {
    "form_name": "",
    "form_list_url": "",
    "form_new_item_url": "",
    "form_settings_url": "",
    "form_site_name": "",
    "form_group_name": "",
    "form_tags": "",
    "form_environment": "",
    "form_description": "",
    "form_favorite": False,
    "form_sort_order": 0,
    "form_url_hint": "",
}

DEFAULT_STATE: dict[str, Any] = {
    "search_query": "",
    "favorites_only": False,
    "selected_groups": [],
    "selected_tags": [],
    "selected_environments": [],
    "group_view": False,
    "dialog": None,
    "target_id": None,
    "import_entries": [],
    "import_policy": DUPLICATE_SKIP,
    "import_source_label": "",
    "flash": [],
}


# ----------------------------------------------------------------------
# 初期化
# ----------------------------------------------------------------------
def get_repository() -> ListRepository:
    """リポジトリを取得する。初回のみDBを初期化する。"""
    repository = ListRepository(DATABASE_PATH)
    if not st.session_state.get("db_ready"):
        repository.initialize()
        st.session_state["db_ready"] = True
    return repository


def init_state() -> None:
    """session_state の既定値を用意する。"""
    for key, value in DEFAULT_STATE.items():
        st.session_state.setdefault(key, value.copy() if isinstance(value, list) else value)


def flash(message: str, level: str = "success") -> None:
    """次の描画で表示するメッセージを積む。"""
    st.session_state["flash"].append((level, message))


def render_flash() -> None:
    """積まれたメッセージを表示して消費する。"""
    messages: list[tuple[str, str]] = st.session_state.get("flash", [])
    for level, message in messages:
        if level == "error":
            st.error(message, icon="⛔")
        elif level == "warning":
            st.warning(message, icon="⚠️")
        else:
            st.success(message, icon="✅")
    st.session_state["flash"] = []


# ----------------------------------------------------------------------
# ダイアログ制御
# ----------------------------------------------------------------------
def prime_form(item: SharePointList | None = None, **overrides: Any) -> None:
    """登録・編集フォームの初期値を session_state へ設定する。

    ウィジェット生成前に呼ぶ必要があるため、ボタンの on_click から使う。
    """
    values = dict(FORM_KEYS)
    if item is not None:
        values.update(
            {
                "form_name": item.name,
                "form_list_url": item.list_url,
                "form_new_item_url": item.new_item_url,
                "form_settings_url": item.settings_url,
                "form_site_name": item.site_name,
                "form_group_name": item.group_name,
                "form_tags": ", ".join(item.tags),
                "form_environment": item.environment,
                "form_description": item.description,
                "form_favorite": item.favorite,
                "form_sort_order": item.sort_order,
            }
        )
    values.update(overrides)
    for key, value in values.items():
        st.session_state[key] = value


def open_create_dialog() -> None:
    prime_form(None)
    st.session_state["dialog"] = "create"
    st.session_state["target_id"] = None


def open_edit_dialog(item: SharePointList) -> None:
    prime_form(item)
    st.session_state["dialog"] = "edit"
    st.session_state["target_id"] = item.id


def open_delete_dialog(list_id: int) -> None:
    st.session_state["dialog"] = "delete"
    st.session_state["target_id"] = list_id


def clear_import_widget_state() -> None:
    """プレビュー用ウィジェットの残存値を消す。

    ウィジェット生成前（ボタンのコールバックや押下直後の分岐）から呼ぶこと。
    """
    for key in [key for key in st.session_state if str(key).startswith("imp_")]:
        del st.session_state[key]


def open_import_dialog(mode: str) -> None:
    st.session_state["dialog"] = mode
    st.session_state["import_entries"] = []
    st.session_state["import_source_label"] = ""
    st.session_state["paste_text"] = ""
    st.session_state.pop("json_upload", None)
    clear_import_widget_state()


def close_dialog() -> None:
    st.session_state["dialog"] = None
    st.session_state["target_id"] = None
    st.session_state["import_entries"] = []
    clear_import_widget_state()


def apply_new_item_suggestion() -> None:
    """一覧URLから新規作成URLの候補を生成してフォームへ入れる（候補にすぎない）。"""
    suggestion = suggest_new_item_url(st.session_state.get("form_list_url", ""))
    if suggestion:
        st.session_state["form_new_item_url"] = suggestion
        st.session_state["form_url_hint"] = "候補を入力しました。内容を確認してください。"
    else:
        st.session_state["form_url_hint"] = (
            "この一覧URLからは候補を生成できませんでした。手入力してください。"
        )


# ----------------------------------------------------------------------
# 登録・編集フォーム
# ----------------------------------------------------------------------
def render_list_form() -> dict[str, Any]:
    """登録・編集フォームを描画し、入力値を返す。"""
    st.text_input("リスト名 *", key="form_name", placeholder="障害管理")
    st.text_input(
        "一覧URL *",
        key="form_list_url",
        placeholder="https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx",
    )

    url_col, hint_col = st.columns([1, 2])
    with url_col:
        st.button(
            "新規作成URLの候補を生成",
            on_click=apply_new_item_suggestion,
            use_container_width=True,
        )
    hint = st.session_state.get("form_url_hint", "")
    if hint:
        with hint_col:
            render_note(hint)

    st.text_input("新規作成URL", key="form_new_item_url")
    st.text_input("設定画面URL", key="form_settings_url")

    left, right = st.columns(2)
    with left:
        st.text_input("サイト名", key="form_site_name")
        st.text_input("グループ", key="form_group_name")
        st.selectbox(
            "環境",
            options=list(ENVIRONMENT_VALUES),
            format_func=environment_label,
            key="form_environment",
        )
    with right:
        st.text_input("タグ（カンマ区切り）", key="form_tags", placeholder="障害, 本番")
        st.number_input("表示順", key="form_sort_order", step=1)
        st.checkbox("お気に入り", key="form_favorite")

    st.text_area("説明", key="form_description", height=80)

    return {
        "name": st.session_state["form_name"],
        "list_url": st.session_state["form_list_url"],
        "new_item_url": st.session_state["form_new_item_url"],
        "settings_url": st.session_state["form_settings_url"],
        "site_name": st.session_state["form_site_name"],
        "group_name": st.session_state["form_group_name"],
        "tags": st.session_state["form_tags"],
        "environment": st.session_state["form_environment"],
        "description": st.session_state["form_description"],
        "favorite": st.session_state["form_favorite"],
        "sort_order": st.session_state["form_sort_order"],
    }


@st.dialog("リストを登録", width="large")
def create_dialog(repository: ListRepository) -> None:
    values = render_list_form()
    save_col, cancel_col = st.columns([1, 1])

    if save_col.button("登録", type="primary", use_container_width=True, key="create_submit"):
        try:
            item = build_list(**values)
            created = repository.create(item)
        except ValidationError as exc:
            st.error(str(exc), icon="⛔")
        except DuplicateUrlError as exc:
            existing = exc.existing
            if existing is not None:
                st.error(
                    f"この一覧URLは「{existing.name}」として既に登録されています。",
                    icon="⛔",
                )
            else:
                st.error(str(exc), icon="⛔")
        except DatabaseError as exc:
            logger.exception("リストの登録に失敗しました")
            st.error(str(exc), icon="⛔")
        else:
            flash(f"「{created.name}」を登録しました。")
            close_dialog()
            st.rerun()

    if cancel_col.button("キャンセル", use_container_width=True, key="create_cancel"):
        close_dialog()
        st.rerun()


@st.dialog("リストを編集", width="large")
def edit_dialog(repository: ListRepository) -> None:
    list_id = st.session_state.get("target_id")
    target = repository.get_by_id(int(list_id)) if list_id is not None else None
    if target is None:
        st.error("編集対象のリストが見つかりませんでした。", icon="⛔")
        if st.button("閉じる", key="edit_missing_close"):
            close_dialog()
            st.rerun()
        return

    values = render_list_form()
    save_col, cancel_col = st.columns([1, 1])

    if save_col.button("更新", type="primary", use_container_width=True, key="edit_submit"):
        try:
            item = build_list(id=target.id, **values)
            updated = repository.update(item)
        except ValidationError as exc:
            st.error(str(exc), icon="⛔")
        except DuplicateUrlError as exc:
            existing = exc.existing
            if existing is not None and existing.id != target.id:
                st.error(
                    f"この一覧URLは「{existing.name}」として既に登録されています。",
                    icon="⛔",
                )
            else:
                st.error(str(exc), icon="⛔")
        except DatabaseError as exc:
            logger.exception("リストの更新に失敗しました")
            st.error(str(exc), icon="⛔")
        else:
            flash(f"「{updated.name}」を更新しました。")
            close_dialog()
            st.rerun()

    if cancel_col.button("キャンセル", use_container_width=True, key="edit_cancel"):
        close_dialog()
        st.rerun()


@st.dialog("削除の確認")
def delete_dialog(repository: ListRepository) -> None:
    list_id = st.session_state.get("target_id")
    target = repository.get_by_id(int(list_id)) if list_id is not None else None
    if target is None:
        st.error("削除対象のリストが見つかりませんでした。", icon="⛔")
        if st.button("閉じる", key="delete_missing_close"):
            close_dialog()
            st.rerun()
        return

    st.warning(f"「{target.name}」を削除しますか？", icon="⚠️")
    st.caption("この操作は取り消せません（ゴミ箱機能はありません）。")

    delete_col, cancel_col = st.columns([1, 1])
    if delete_col.button("削除する", type="primary", use_container_width=True, key="delete_submit"):
        try:
            deleted = repository.delete(int(target.id or 0))
        except DatabaseError as exc:
            logger.exception("リストの削除に失敗しました")
            st.error(str(exc), icon="⛔")
        else:
            if deleted:
                flash(f"「{target.name}」を削除しました。")
            else:
                flash("削除対象が見つかりませんでした。", "warning")
            close_dialog()
            st.rerun()

    if cancel_col.button("キャンセル", use_container_width=True, key="delete_cancel"):
        close_dialog()
        st.rerun()


# ----------------------------------------------------------------------
# インポート
# ----------------------------------------------------------------------
def entry_to_state(entry: ParsedEntry) -> dict[str, Any]:
    """プレビュー用に ParsedEntry を素の辞書へ変換する。"""
    return {
        "name": entry.name,
        "list_url": entry.list_url,
        "new_item_url": entry.new_item_url,
        "settings_url": entry.settings_url,
        "site_name": entry.site_name,
        "group_name": entry.group_name,
        "tags": ", ".join(entry.tags),
        "environment": entry.environment,
        "description": entry.description,
        "favorite": entry.favorite,
        "sort_order": entry.sort_order,
        "source": entry.source,
        "errors": list(entry.errors),
    }


def store_parse_result(entries: Iterable[ParsedEntry], source_label: str) -> None:
    """解析結果をプレビュー用の状態として保存する（前回の入力は破棄する）。"""
    clear_import_widget_state()
    st.session_state["import_entries"] = [entry_to_state(entry) for entry in entries]
    st.session_state["import_source_label"] = source_label


def render_import_preview(repository: ListRepository) -> None:
    """解析結果のプレビューを描画し、確定した行だけを保存する。"""
    entries: list[dict[str, Any]] = st.session_state.get("import_entries", [])
    if not entries:
        return

    st.markdown("---")
    render_section_heading("インポートプレビュー", len(entries))
    st.caption("内容を確認・修正し、取り込む行にチェックを入れて保存してください。")

    for index, entry in enumerate(entries):
        stored = repository.get_by_url(entry["list_url"]) if entry["list_url"] else None
        title = entry["name"] or "（リスト名なし）"
        label = f"{index + 1}. {title}"
        if stored is not None:
            label += "  ⟳ 重複"
        if entry["errors"]:
            label += "  ⛔ 要確認"

        with st.expander(label, expanded=True):
            st.checkbox(
                "取り込む",
                key=f"imp_use_{index}",
                value=not entry["errors"],
            )
            st.text_input("リスト名", key=f"imp_name_{index}", value=entry["name"])
            st.text_input("一覧URL", key=f"imp_url_{index}", value=entry["list_url"])
            st.text_input(
                "新規作成URL", key=f"imp_new_{index}", value=entry["new_item_url"]
            )
            col_left, col_right = st.columns(2)
            with col_left:
                st.text_input(
                    "グループ", key=f"imp_group_{index}", value=entry["group_name"]
                )
            with col_right:
                st.text_input("タグ（カンマ区切り）", key=f"imp_tags_{index}", value=entry["tags"])

            st.caption(f"解析形式: {entry['source']}")
            if stored is not None:
                render_note(
                    f"既に登録済みです（現在の名称: {stored.name}）。"
                    f"重複時の動作: {DUPLICATE_POLICY_LABELS[st.session_state['import_policy']]}",
                    "warn",
                )
            for error in entry["errors"]:
                render_note(error, "error")

    st.radio(
        "重複（一覧URLが同じ）の場合の動作",
        options=[DUPLICATE_SKIP, DUPLICATE_UPDATE, DUPLICATE_ERROR],
        format_func=lambda value: DUPLICATE_POLICY_LABELS[value],
        key="import_policy",
        horizontal=True,
    )

    save_col, cancel_col = st.columns([1, 1])
    if save_col.button(
        "選択した内容を保存", type="primary", use_container_width=True, key="import_submit"
    ):
        commit_import(repository, entries)

    if cancel_col.button("キャンセル", use_container_width=True, key="import_cancel"):
        close_dialog()
        st.rerun()


def collect_selected_items(
    entries: list[dict[str, Any]]
) -> tuple[list[SharePointList], list[str]]:
    """プレビューで選択された行を検証し、保存対象と入力エラーへ振り分ける。"""
    items: list[SharePointList] = []
    errors: list[str] = []

    for index, entry in enumerate(entries):
        if not st.session_state.get(f"imp_use_{index}", False):
            continue

        label = st.session_state.get(f"imp_name_{index}", "") or f"{index + 1}件目"
        try:
            items.append(
                build_list(
                    name=st.session_state.get(f"imp_name_{index}", ""),
                    list_url=st.session_state.get(f"imp_url_{index}", ""),
                    new_item_url=st.session_state.get(f"imp_new_{index}", ""),
                    settings_url=entry["settings_url"],
                    site_name=entry["site_name"],
                    group_name=st.session_state.get(f"imp_group_{index}", ""),
                    tags=st.session_state.get(f"imp_tags_{index}", ""),
                    environment=entry["environment"],
                    description=entry["description"],
                    favorite=entry["favorite"],
                    sort_order=entry["sort_order"],
                )
            )
        except ValidationError as exc:
            errors.append(f"{label}: {exc}")

    return items, errors


def commit_import(repository: ListRepository, entries: list[dict[str, Any]]) -> None:
    """プレビューで確定された行を保存する。"""
    items, errors = collect_selected_items(entries)

    if not items and not errors:
        flash("取り込む行が選択されていません。", "warning")
        st.rerun()

    summary = save_import_items(repository, items, st.session_state["import_policy"])
    errors.extend(summary.errors)
    if summary.errors:
        logger.warning("インポート中に保存できなかった行があります: %d件", len(summary.errors))

    if summary.saved:
        flash(
            f"インポートが完了しました（新規 {summary.created}件 / 更新 {summary.updated}件"
            f" / スキップ {summary.skipped}件）。"
        )
    elif summary.skipped:
        flash(f"すべてスキップしました（{summary.skipped}件）。", "warning")

    for message in errors[:10]:
        flash(message, "error")
    if len(errors) > 10:
        flash(f"他 {len(errors) - 10}件のエラーがあります。", "error")

    close_dialog()
    st.rerun()


@st.dialog("貼り付けインポート", width="large")
def paste_import_dialog(repository: ListRepository) -> None:
    st.caption(
        "Bookmarkletの出力JSON、Markdownリンク、HTMLリンク、"
        "「名前とURL」、URLのみ に対応しています。"
    )
    st.text_area("貼り付け内容", key="paste_text", height=180)

    parse_col, cancel_col = st.columns([1, 1])
    if parse_col.button("解析する", type="primary", use_container_width=True, key="paste_parse"):
        result = parse_import_text(st.session_state.get("paste_text", ""))
        store_parse_result(result.entries, "貼り付け")
        for message in result.errors:
            st.error(message, icon="⛔")

    if cancel_col.button("閉じる", use_container_width=True, key="paste_close"):
        close_dialog()
        st.rerun()

    render_import_preview(repository)


@st.dialog("JSONバックアップの復元", width="large")
def json_import_dialog(repository: ListRepository) -> None:
    st.caption("エクスポートしたJSONファイルを選択してください。")
    uploaded = st.file_uploader("JSONファイル", type=["json"], key="json_upload")

    parse_col, cancel_col = st.columns([1, 1])
    if parse_col.button(
        "読み込む", type="primary", use_container_width=True, key="json_parse", disabled=uploaded is None
    ):
        if uploaded is not None:
            try:
                text = uploaded.getvalue().decode("utf-8")
            except UnicodeDecodeError:
                st.error("ファイルをUTF-8として読み取れませんでした。", icon="⛔")
            else:
                result = parse_json_text(text)
                store_parse_result(result.entries, uploaded.name)
                for message in result.errors:
                    st.error(message, icon="⛔")

    if cancel_col.button("閉じる", use_container_width=True, key="json_close"):
        close_dialog()
        st.rerun()

    render_import_preview(repository)


# ----------------------------------------------------------------------
# タイル表示
# ----------------------------------------------------------------------
def toggle_favorite(repository: ListRepository, item: SharePointList) -> None:
    try:
        repository.set_favorite(int(item.id or 0), not item.favorite)
    except DatabaseError as exc:
        logger.exception("お気に入りの更新に失敗しました")
        flash(str(exc), "error")


def render_tile(repository: ListRepository, item: SharePointList) -> None:
    """1件のリストをタイルとして描画する。"""
    with st.container(key=f"ln-tile-{item.id}", border=True):
        title_col, fav_col = st.columns([6, 1])
        with title_col:
            render_title(item.name)
        with fav_col:
            star = "★" if item.favorite else "☆"
            if st.button(
                star,
                key=f"fav_{item.id}",
                help="お気に入りを切り替える",
                use_container_width=True,
            ):
                toggle_favorite(repository, item)
                st.rerun()

        render_meta_row(
            [
                chip(item.site_name, "site") if item.site_name else "",
                chip(item.group_name or UNCATEGORIZED_GROUP, "group"),
                environment_chip(item.environment),
                *[chip(tag, "tag") for tag in item.tags],
            ]
        )
        render_description(item.description)

        open_col, new_col, settings_col = st.columns(3)
        with open_col:
            st.link_button("一覧", item.list_url, use_container_width=True)
        with new_col:
            if item.new_item_url:
                st.link_button("新規作成", item.new_item_url, use_container_width=True)
            else:
                st.button(
                    "新規作成",
                    key=f"new_disabled_{item.id}",
                    disabled=True,
                    help="新規作成URLが未登録です",
                    use_container_width=True,
                )
        with settings_col:
            if item.settings_url:
                st.link_button("設定", item.settings_url, use_container_width=True)
            else:
                st.button(
                    "設定",
                    key=f"settings_disabled_{item.id}",
                    disabled=True,
                    help="設定URLが未登録です",
                    use_container_width=True,
                )

        edit_col, delete_col = st.columns(2)
        edit_col.button(
            "編集",
            key=f"edit_{item.id}",
            on_click=open_edit_dialog,
            args=(item,),
            use_container_width=True,
        )
        delete_col.button(
            "削除",
            key=f"delete_{item.id}",
            on_click=open_delete_dialog,
            args=(item.id,),
            use_container_width=True,
        )


def render_tiles(repository: ListRepository, items: list[SharePointList]) -> None:
    """タイルをグリッド状に並べる。"""
    for row_start in range(0, len(items), TILE_COLUMNS):
        row_items = items[row_start : row_start + TILE_COLUMNS]
        columns = st.columns(TILE_COLUMNS, gap="medium")
        for column, item in zip(columns, row_items):
            with column:
                render_tile(repository, item)


# ----------------------------------------------------------------------
# サイドバー・ヘッダー
# ----------------------------------------------------------------------
def render_sidebar(repository: ListRepository, total: int, shown: int) -> None:
    with st.sidebar:
        st.markdown("### フィルター")
        st.checkbox("お気に入りのみ", key="favorites_only")
        st.checkbox("グループごとに表示", key="group_view")

        group_options = repository.group_names() + [UNCATEGORIZED_GROUP]
        st.multiselect("グループ", options=group_options, key="selected_groups")
        st.multiselect("タグ", options=repository.tag_names(), key="selected_tags")
        st.multiselect(
            "環境",
            options=repository.environments(),
            format_func=environment_label,
            key="selected_environments",
        )

        st.button("フィルターをすべて解除", use_container_width=True, on_click=reset_filters)

        st.markdown("---")
        st.caption(f"表示 {shown} / 登録 {total} 件")
        st.caption(f"DB: {DATABASE_PATH}")


def reset_filters() -> None:
    st.session_state["search_query"] = ""
    st.session_state["favorites_only"] = False
    st.session_state["selected_groups"] = []
    st.session_state["selected_tags"] = []
    st.session_state["selected_environments"] = []


def build_export_bytes(items: list[SharePointList]) -> bytes:
    """エクスポート用JSONのバイト列を作る。"""
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "exportedAt": now_iso(),
        "lists": [to_export_dict(item) for item in items],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def render_header(items: list[SharePointList]) -> None:
    render_brand()
    search_col, create_col, paste_col, json_col, export_col = st.columns([5, 1.3, 1.5, 1.5, 1.5])

    with search_col:
        st.text_input(
            "検索",
            key="search_query",
            placeholder="リスト名 / サイト名 / グループ / タグ / 説明 / URL",
            label_visibility="collapsed",
        )
    create_col.button(
        "＋ 登録", type="primary", use_container_width=True, on_click=open_create_dialog
    )
    paste_col.button(
        "貼り付け取込", use_container_width=True, on_click=open_import_dialog, args=("paste",)
    )
    json_col.button(
        "JSON復元", use_container_width=True, on_click=open_import_dialog, args=("json",)
    )
    with export_col:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        st.download_button(
            "バックアップ",
            data=build_export_bytes(items),
            file_name=f"list-nexus-backup-{timestamp}.json",
            mime="application/json",
            use_container_width=True,
            disabled=not items,
        )


# ----------------------------------------------------------------------
# メイン
# ----------------------------------------------------------------------
def render_body(repository: ListRepository, items: list[SharePointList]) -> None:
    filtered = filter_lists(
        items,
        query=st.session_state["search_query"],
        favorites_only=st.session_state["favorites_only"],
        groups=st.session_state["selected_groups"],
        tags=st.session_state["selected_tags"],
        environments=st.session_state["selected_environments"],
    )

    render_sidebar(repository, total=len(items), shown=len(filtered))

    if not items:
        render_note(
            "まだリストが登録されていません。"
            "右上の「＋ 登録」またはBookmarkletの出力を「貼り付け取込」から登録してください。"
        )
        return

    if not filtered:
        render_note("条件に一致するリストがありません。検索語やフィルターを見直してください。", "warn")
        return

    if st.session_state["group_view"]:
        for group_name, group_items in group_by_group_name(filtered):
            render_section_heading(group_name, len(group_items))
            render_tiles(repository, group_items)
        return

    favorites = [item for item in filtered if item.favorite]
    others = [item for item in filtered if not item.favorite]

    if favorites:
        render_section_heading("★ お気に入り", len(favorites))
        render_tiles(repository, favorites)
    if others:
        render_section_heading("すべてのリスト" if favorites else "リスト", len(others))
        render_tiles(repository, others)


def render_dialogs(repository: ListRepository) -> None:
    dialog = st.session_state.get("dialog")
    if dialog == "create":
        create_dialog(repository)
    elif dialog == "edit":
        edit_dialog(repository)
    elif dialog == "delete":
        delete_dialog(repository)
    elif dialog == "paste":
        paste_import_dialog(repository)
    elif dialog == "json":
        json_import_dialog(repository)


def main() -> None:
    st.set_page_config(
        page_title=APP_NAME,
        page_icon=APP_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_styles()
    init_state()

    try:
        repository = get_repository()
        items = repository.list_all()
    except DatabaseError as exc:
        logger.exception("データベースの初期化に失敗しました")
        st.error(str(exc), icon="⛔")
        st.stop()
        return

    render_header(items)
    render_flash()

    try:
        render_body(repository, items)
        render_dialogs(repository)
    except DatabaseError as exc:
        logger.exception("データベース操作に失敗しました")
        st.error(str(exc), icon="⛔")


if __name__ == "__main__":
    main()

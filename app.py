"""LIST NEXUS - SharePoint Listリンクのローカルランチャー（Streamlit UI）.

UIはこのモジュールに閉じ込め、SQLやテキスト解析は
repositories / import_parser / url_utils に委譲する。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Iterable, Sequence

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
    render_group_bar,
    render_link_row,
    render_meta_row,
    render_note,
    render_row_summary,
    render_section_heading,
    render_title,
)

logger = logging.getLogger("list_nexus")

TILE_COLUMNS = 3

# 表示スタイル
VIEW_LIST = "リスト"
VIEW_TILE = "タイル"
VIEW_TABLE = "表（編集）"
VIEW_MODES: tuple[str, ...] = (VIEW_LIST, VIEW_TILE, VIEW_TABLE)

# 1画面に描画するタイルの既定数。Streamlitは1クリックごとに全ウィジェットを
# 再描画するため、件数が多いと操作が重くなる。既定を抑えて「さらに表示」で伸ばす。
PAGE_SIZE = 50

# 登録・編集ダイアログのウィジェットキー
FORM_KEYS: dict[str, Any] = {
    "form_name": "",
    "form_list_url": "",
    "form_settings_url": "",
    "form_site_name": "",
    "form_group_name": "",
    "form_tags": "",
    "form_environment": "",
    "form_description": "",
    "form_favorite": False,
    "form_sort_order": 0,
}

DEFAULT_STATE: dict[str, Any] = {
    "search_query": "",
    "favorites_only": False,
    "selected_groups": [],
    "selected_tags": [],
    "selected_environments": [],
    "group_view": True,
    "view_mode": VIEW_LIST,
    "collapsed_groups": [],
    "visible_count": PAGE_SIZE,
    "dialog": None,
    "target_id": None,
    "bulk_target_ids": [],
    "bulk_target_label": "",
    "table_rows": [],
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


def open_bulk_delete_dialog(ids: Sequence[int], label: str) -> None:
    """まとめて削除の確認ダイアログを開く。"""
    st.session_state["dialog"] = "bulk_delete"
    st.session_state["bulk_target_ids"] = [int(value) for value in ids]
    st.session_state["bulk_target_label"] = label
    st.session_state["bulk_confirmed"] = False


def clear_import_widget_state() -> None:
    """プレビュー表の残存値を消す。

    ウィジェット生成前（ボタンのコールバックや押下直後の分岐）から呼ぶこと。
    """
    for key in [key for key in st.session_state if str(key).startswith("imp_")]:
        del st.session_state[key]
    st.session_state["import_rows"] = []


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
    st.session_state["bulk_target_ids"] = []
    st.session_state["bulk_target_label"] = ""
    st.session_state["import_entries"] = []
    clear_import_widget_state()


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
            # new_item_url は画面で扱わないが、既存の値は消さずに引き継ぐ。
            item = build_list(id=target.id, new_item_url=target.new_item_url, **values)
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


# まとめて削除で、追加確認（チェックボックス）を要求する件数のしきい値。
BULK_CONFIRM_THRESHOLD = 10


@st.dialog("まとめて削除の確認", width="large")
def bulk_delete_dialog(repository: ListRepository) -> None:
    ids: list[int] = st.session_state.get("bulk_target_ids", [])
    label: str = st.session_state.get("bulk_target_label", "")

    targets = [item for item in (repository.get_by_id(list_id) for list_id in ids) if item]
    if not targets:
        st.error("削除対象のリストが見つかりませんでした。", icon="⛔")
        if st.button("閉じる", key="bulk_missing_close"):
            close_dialog()
            st.rerun()
        return

    st.warning(f"{label}{len(targets)}件を削除しますか？", icon="⚠️")
    st.caption("この操作は取り消せません（ゴミ箱機能はありません）。")

    names = [item.name for item in targets]
    for name in names[:5]:
        st.markdown(f"- {name}")
    if len(names) > 5:
        with st.expander(f"残り{len(names) - 5}件を表示"):
            st.markdown("\n".join(f"- {name}" for name in names[5:]))

    ready = True
    if len(targets) >= BULK_CONFIRM_THRESHOLD:
        ready = st.checkbox(
            "件数と内容を確認しました（必要なら先に「バックアップ」で書き出してください）",
            key="bulk_confirmed",
        )

    delete_col, cancel_col = st.columns([1, 1])
    if delete_col.button(
        f"{len(targets)}件を削除する",
        type="primary",
        use_container_width=True,
        disabled=not ready,
        key="bulk_delete_submit",
    ):
        try:
            deleted = repository.delete_many([int(item.id or 0) for item in targets])
        except DatabaseError as exc:
            logger.exception("リストの一括削除に失敗しました")
            st.error(str(exc), icon="⛔")
        else:
            flash(f"{deleted}件を削除しました。")
            st.session_state["visible_count"] = PAGE_SIZE
            close_dialog()
            st.rerun()

    if cancel_col.button("キャンセル", use_container_width=True, key="bulk_delete_cancel"):
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


def build_preview_rows(
    repository: ListRepository, entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """プレビュー表の行データを作る（状態列は読み取り専用）。"""
    rows: list[dict[str, Any]] = []
    for entry in entries:
        stored = repository.get_by_url(entry["list_url"]) if entry["list_url"] else None
        if entry["errors"]:
            status = "⛔ " + " / ".join(entry["errors"])
        elif stored is not None:
            status = f"⟳ 登録済み: {stored.name}"
        else:
            status = "✓ 新規"
        rows.append(
            {
                "取込": not entry["errors"],
                "リスト名": entry["name"],
                "一覧URL": entry["list_url"],
                "サイト名": entry["site_name"],
                "グループ": entry["group_name"],
                "タグ": entry["tags"],
                "状態": status,
            }
        )
    return rows


def render_import_preview(repository: ListRepository) -> None:
    """解析結果のプレビューを表形式で描画し、確定した行だけを保存する。

    件数が多くても軽く扱えるよう、行ごとにウィジェットを作らず
    st.data_editor 1つにまとめている。
    """
    entries: list[dict[str, Any]] = st.session_state.get("import_entries", [])
    if not entries:
        return

    st.markdown("---")
    render_section_heading("インポートプレビュー", len(entries))
    st.caption(
        "表を直接編集できます。「取込」にチェックした行だけを保存します。"
        "セルをダブルクリックで修正、ヘッダーで並べ替えできます。"
    )

    rows = build_preview_rows(repository, entries)
    invalid_count = sum(1 for entry in entries if entry["errors"])
    duplicate_count = sum(1 for row in rows if row["状態"].startswith("⟳"))
    if invalid_count:
        render_note(f"{invalid_count}件に問題があります（状態列を確認してください）。", "error")
    if duplicate_count:
        render_note(
            f"{duplicate_count}件は既に登録済みです。下の「重複の場合の動作」が適用されます。", "warn"
        )

    edited = st.data_editor(
        rows,
        key="imp_table",
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        height=min(80 + 36 * len(rows), 460),
        disabled=["状態"],
        column_config={
            "取込": st.column_config.CheckboxColumn("取込", width="small"),
            "リスト名": st.column_config.TextColumn("リスト名", width="medium"),
            "一覧URL": st.column_config.TextColumn("一覧URL", width="large"),
            "サイト名": st.column_config.TextColumn("サイト名", width="small"),
            "グループ": st.column_config.TextColumn("グループ", width="small"),
            "タグ": st.column_config.TextColumn("タグ（カンマ区切り）", width="small"),
            "状態": st.column_config.TextColumn("状態", width="medium"),
        },
    )
    st.session_state["import_rows"] = edited

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
    entries: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> tuple[list[SharePointList], list[str]]:
    """プレビュー表で選択された行を検証し、保存対象と入力エラーへ振り分ける。

    表で編集できる列（リスト名・URL・サイト名・グループ・タグ）は表の値を使い、
    それ以外（環境・説明・お気に入り・表示順・新規作成URL）は解析結果を引き継ぐ。
    """
    items: list[SharePointList] = []
    errors: list[str] = []

    for index, row in enumerate(rows):
        if not row.get("取込"):
            continue
        entry = entries[index] if index < len(entries) else {}
        label = str(row.get("リスト名") or "").strip() or f"{index + 1}件目"
        try:
            items.append(
                build_list(
                    name=row.get("リスト名"),
                    list_url=row.get("一覧URL"),
                    new_item_url=entry.get("new_item_url", ""),
                    settings_url=entry.get("settings_url", ""),
                    site_name=row.get("サイト名"),
                    group_name=row.get("グループ"),
                    tags=row.get("タグ"),
                    environment=entry.get("environment", ""),
                    description=entry.get("description", ""),
                    favorite=bool(entry.get("favorite", False)),
                    sort_order=entry.get("sort_order", 0),
                )
            )
        except ValidationError as exc:
            errors.append(f"{label}: {exc}")

    return items, errors


def commit_import(repository: ListRepository, entries: list[dict[str, Any]]) -> None:
    """プレビューで確定された行を保存する。"""
    rows: list[dict[str, Any]] = st.session_state.get("import_rows", [])
    items, errors = collect_selected_items(entries, rows)

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

        # リンクはウィジェットを使わずアンカーで描画する（件数が増えても軽い）。
        render_link_row([("開く", item.list_url), ("設定", item.settings_url)])

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
# リスト行表示
# ----------------------------------------------------------------------
def render_list_row(repository: ListRepository, item: SharePointList) -> None:
    """1件を1行で描画する。

    行あたりのウィジェットは ★ / 編集 / 削除 の3つに抑え、
    リンクはアンカー、URLのコピーは st.code の標準コピーボタンで賄う。
    """
    with st.container(key=f"ln-row-{item.id}"):
        star_col, main_col, url_col, link_col, edit_col, delete_col = st.columns(
            [0.35, 5.2, 3.0, 1.7, 0.45, 0.45], vertical_alignment="center"
        )

        with star_col:
            if st.button(
                "★" if item.favorite else "☆",
                key=f"fav_{item.id}",
                help="お気に入りを切り替える",
            ):
                toggle_favorite(repository, item)
                st.rerun()

        with main_col:
            render_row_summary(
                item.name,
                item.description,
                [
                    chip(item.site_name, "site") if item.site_name else "",
                    chip(item.group_name or UNCATEGORIZED_GROUP, "group"),
                    environment_chip(item.environment),
                    *[chip(tag, "tag") for tag in item.tags],
                ],
            )

        with url_col:
            # st.code の標準コピーボタンでURLをコピーできる（ウィジェットを増やさない）。
            st.code(item.list_url, language=None, wrap_lines=False)

        with link_col:
            render_link_row([("開く", item.list_url), ("設定", item.settings_url)])

        edit_col.button(
            ":material/edit:",
            key=f"edit_{item.id}",
            help="編集",
            on_click=open_edit_dialog,
            args=(item,),
        )
        delete_col.button(
            ":material/delete:",
            key=f"delete_{item.id}",
            help="削除",
            on_click=open_delete_dialog,
            args=(item.id,),
        )


def render_list_rows(repository: ListRepository, items: list[SharePointList]) -> None:
    for item in items:
        render_list_row(repository, item)


def render_items(repository: ListRepository, items: list[SharePointList]) -> None:
    """表示スタイルに応じてタイルまたはリスト行で描画する。"""
    if st.session_state["view_mode"] == VIEW_TILE:
        render_tiles(repository, items)
    else:
        render_list_rows(repository, items)


# ----------------------------------------------------------------------
# グループの折りたたみ
# ----------------------------------------------------------------------
def toggle_group(group_name: str) -> None:
    collapsed: list[str] = list(st.session_state.get("collapsed_groups", []))
    if group_name in collapsed:
        collapsed.remove(group_name)
    else:
        collapsed.append(group_name)
    st.session_state["collapsed_groups"] = collapsed


def set_all_groups_collapsed(group_names: Sequence[str], collapsed: bool) -> None:
    st.session_state["collapsed_groups"] = list(group_names) if collapsed else []


# ----------------------------------------------------------------------
# 表ビュー（まとめて管理）
# ----------------------------------------------------------------------
# 表で編集できる列（この列だけを差分判定と保存の対象にする）
TABLE_EDITABLE_COLUMNS: tuple[str, ...] = (
    "★",
    "リスト名",
    "サイト名",
    "グループ",
    "環境",
    "タグ",
    "表示順",
)

# 環境は日本語ラベルで選ばせ、保存時に内部値へ戻す。
ENVIRONMENT_OPTIONS: list[str] = [environment_label(value) for value in ENVIRONMENT_VALUES]
LABEL_TO_ENVIRONMENT: dict[str, str] = {
    environment_label(value): value for value in ENVIRONMENT_VALUES
}


def build_table_rows(items: list[SharePointList]) -> list[dict[str, Any]]:
    """表ビュー用の行データを作る。

    ID列は画面には出さず、編集結果を元のレコードへ突き合わせるために使う
    （表を並べ替えても行の対応がずれないようにするため）。
    """
    return [
        {
            "ID": item.id,
            "選択": False,
            "★": item.favorite,
            "リスト名": item.name,
            "サイト名": item.site_name,
            "グループ": item.group_name,
            "環境": environment_label(item.environment),
            "タグ": ", ".join(item.tags),
            "表示順": item.sort_order,
            "開く": item.list_url,
            "設定": item.settings_url,
        }
        for item in items
    ]


def _as_int(value: Any) -> Any:
    """表のセル値を整数向けに整える（空欄やNaNは0にする）。"""
    if value is None or value == "":
        return 0
    if isinstance(value, float) and value != value:  # NaN
        return 0
    return value


def collect_table_updates(
    items: list[SharePointList], rows: list[dict[str, Any]]
) -> tuple[list[SharePointList], list[str]]:
    """表の編集結果から、変更があった行だけを検証済みモデルにして返す。

    表に出していない項目（URL・説明・新規作成URL）は既存の値を引き継ぐ。
    検証に失敗した行はエラーメッセージにして、他の行の保存は続行する。
    """
    by_id = {item.id: item for item in items}
    original_by_id = {row["ID"]: row for row in build_table_rows(items)}

    updates: list[SharePointList] = []
    errors: list[str] = []

    for row in rows:
        item = by_id.get(row.get("ID"))
        if item is None:
            continue
        before = original_by_id[item.id]
        if all(row.get(column) == before.get(column) for column in TABLE_EDITABLE_COLUMNS):
            continue

        label = str(before.get("リスト名") or item.name)
        try:
            updates.append(
                build_list(
                    id=item.id,
                    name=row.get("リスト名"),
                    list_url=item.list_url,
                    new_item_url=item.new_item_url,
                    settings_url=item.settings_url,
                    site_name=row.get("サイト名"),
                    group_name=row.get("グループ"),
                    tags=row.get("タグ"),
                    environment=LABEL_TO_ENVIRONMENT.get(str(row.get("環境") or ""), ""),
                    description=item.description,
                    favorite=bool(row.get("★")),
                    sort_order=_as_int(row.get("表示順")),
                )
            )
        except ValidationError as exc:
            errors.append(f"{label}: {exc}")

    return updates, errors


def save_table_edits(repository: ListRepository, items: list[SharePointList]) -> None:
    """表の編集内容を保存する。"""
    rows: list[dict[str, Any]] = st.session_state.get("table_rows", [])
    updates, errors = collect_table_updates(items, rows)

    saved = 0
    for item in updates:
        try:
            repository.update(item)
            saved += 1
        except (DuplicateUrlError, DatabaseError) as exc:
            logger.exception("表からの更新に失敗しました")
            errors.append(f"{item.name}: {exc}")

    if saved:
        flash(f"{saved}件を更新しました。")
    for message in errors[:10]:
        flash(message, "error")
    if len(errors) > 10:
        flash(f"他 {len(errors) - 10}件のエラーがあります。", "error")
    if not saved and not errors:
        flash("変更はありませんでした。", "warning")

    # 編集の保留状態を消してから再描画する（保存済みの編集が残らないように）。
    st.session_state.pop("manage_table", None)


def render_table_view(repository: ListRepository, items: list[SharePointList]) -> None:
    """一覧を表で表示し、まとめて編集・削除できるようにする。

    行ごとにウィジェットを作らないため、件数が多くても軽い。
    """
    render_section_heading("表でまとめて管理", len(items))
    st.caption(
        "セルをダブルクリックで編集し、「変更を保存」で反映します。"
        "削除は「選択」にチェックを入れてから行ってください。"
        "URLと説明はこの表では変更できません（タイルの「編集」から変更してください）。"
    )

    edited = st.data_editor(
        build_table_rows(items),
        key="manage_table",
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        height=min(120 + 35 * len(items), 620),
        disabled=["開く", "設定"],
        column_config={
            "ID": None,
            "選択": st.column_config.CheckboxColumn("選択", width="small", help="削除する行"),
            "★": st.column_config.CheckboxColumn("★", width="small", help="お気に入り"),
            "リスト名": st.column_config.TextColumn("リスト名", width="large", required=True),
            "サイト名": st.column_config.TextColumn("サイト名", width="small"),
            "グループ": st.column_config.TextColumn(
                "グループ", width="small", help="空欄は未分類として扱います"
            ),
            "環境": st.column_config.SelectboxColumn(
                "環境", width="small", options=ENVIRONMENT_OPTIONS
            ),
            "タグ": st.column_config.TextColumn("タグ", width="medium", help="カンマ区切り"),
            "表示順": st.column_config.NumberColumn("表示順", width="small", step=1),
            "開く": st.column_config.LinkColumn("開く", display_text="一覧", width="small"),
            "設定": st.column_config.LinkColumn("設定", display_text="設定", width="small"),
        },
    )
    st.session_state["table_rows"] = edited

    pending, _ = collect_table_updates(items, edited)
    selected_ids = [row.get("ID") for row in edited if row.get("選択")]

    save_col, selected_col, all_col, _ = st.columns([1.5, 1.5, 1.6, 2])
    save_col.button(
        f"変更を保存（{len(pending)}件）" if pending else "変更を保存",
        type="primary" if pending else "secondary",
        use_container_width=True,
        disabled=not pending,
        key="table_save",
        on_click=save_table_edits,
        args=(repository, items),
    )
    selected_col.button(
        f"選択した{len(selected_ids)}件を削除" if selected_ids else "選択した行を削除",
        use_container_width=True,
        disabled=not selected_ids,
        key="table_delete_selected",
        on_click=open_bulk_delete_dialog,
        args=(selected_ids, "選択した "),
    )
    all_col.button(
        f"表示中の{len(items)}件をすべて削除",
        use_container_width=True,
        key="table_delete_all",
        help="サイドバーのフィルターで絞り込んでから使うと、グループ単位・タグ単位でまとめて削除できます。",
        on_click=open_bulk_delete_dialog,
        args=([item.id for item in items], "表示中の "),
    )


# ----------------------------------------------------------------------
# サイドバー・ヘッダー
# ----------------------------------------------------------------------
def select_group(group_name: str) -> None:
    """サイドバーのグループ一覧から絞り込みを切り替える（同じものを押すと解除）。"""
    current = st.session_state.get("selected_groups", [])
    if not group_name:
        st.session_state["selected_groups"] = []
    elif current == [group_name]:
        st.session_state["selected_groups"] = []
    else:
        st.session_state["selected_groups"] = [group_name]
    reset_visible_count()


def render_group_nav(items: list[SharePointList]) -> None:
    """サイドバーにグループ一覧（件数つき）を出す。"""
    counts: dict[str, int] = {}
    for item in items:
        key = item.group_name.strip() or UNCATEGORIZED_GROUP
        counts[key] = counts.get(key, 0) + 1

    names = sorted((name for name in counts if name != UNCATEGORIZED_GROUP), key=str.casefold)
    if UNCATEGORIZED_GROUP in counts:
        names.append(UNCATEGORIZED_GROUP)

    selected = st.session_state.get("selected_groups", [])
    st.button(
        f"すべて（{len(items)}）",
        key="group_nav_all",
        use_container_width=True,
        type="primary" if not selected else "secondary",
        on_click=select_group,
        args=("",),
    )
    for name in names:
        st.button(
            f"{name}（{counts[name]}）",
            key=f"group_nav_{name}",
            use_container_width=True,
            type="primary" if selected == [name] else "secondary",
            on_click=select_group,
            args=(name,),
        )


def render_sidebar(
    repository: ListRepository,
    items: list[SharePointList],
    total: int,
    shown: int,
) -> None:
    with st.sidebar:
        st.markdown("### 表示")
        st.radio(
            "表示スタイル",
            options=list(VIEW_MODES),
            key="view_mode",
            label_visibility="collapsed",
        )
        if st.session_state["view_mode"] != VIEW_TABLE:
            st.checkbox("グループごとに区切る", key="group_view")

        st.markdown("### グループ")
        render_group_nav(items)

        st.markdown("### フィルター")
        st.checkbox("お気に入りのみ", key="favorites_only", on_change=reset_visible_count)
        st.multiselect(
            "タグ",
            options=repository.tag_names(),
            key="selected_tags",
            on_change=reset_visible_count,
        )
        st.multiselect(
            "環境",
            options=repository.environments(),
            format_func=environment_label,
            key="selected_environments",
            on_change=reset_visible_count,
        )

        st.button("フィルターをすべて解除", use_container_width=True, on_click=reset_filters)

        st.markdown("---")
        st.caption(f"表示 {shown} / 登録 {total} 件")
        st.caption(f"DB: {DATABASE_PATH}")


def reset_visible_count() -> None:
    """絞り込みが変わったら表示件数を既定へ戻す。"""
    st.session_state["visible_count"] = PAGE_SIZE


def reset_filters() -> None:
    st.session_state["search_query"] = ""
    st.session_state["favorites_only"] = False
    st.session_state["selected_groups"] = []
    st.session_state["selected_tags"] = []
    st.session_state["selected_environments"] = []
    reset_visible_count()


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
    search_col, create_col, paste_col, json_col, export_col = st.columns(
        [9, 1.8, 0.5, 0.5, 0.5], vertical_alignment="center"
    )

    with search_col:
        st.text_input(
            "検索",
            key="search_query",
            placeholder="リスト名 / サイト名 / グループ / タグ / 説明 / URL",
            label_visibility="collapsed",
            on_change=reset_visible_count,
        )
    create_col.button(
        "登録",
        icon=":material/add:",
        type="primary",
        use_container_width=True,
        on_click=open_create_dialog,
    )
    paste_col.button(
        ":material/content_paste:",
        help="貼り付け取込（Bookmarkletの出力やExcelのタブ区切り）",
        on_click=open_import_dialog,
        args=("paste",),
    )
    json_col.button(
        ":material/restore:",
        help="JSONバックアップから復元",
        on_click=open_import_dialog,
        args=("json",),
    )
    with export_col:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        st.download_button(
            ":material/download:",
            help="JSONバックアップをダウンロード",
            data=build_export_bytes(items),
            file_name=f"list-nexus-backup-{timestamp}.json",
            mime="application/json",
            disabled=not items,
        )


# ----------------------------------------------------------------------
# メイン
# ----------------------------------------------------------------------
def render_group_section(
    repository: ListRepository,
    index: int,
    group_name: str,
    group_items: list[SharePointList],
    group_all: list[SharePointList],
) -> None:
    """グループ見出し（折りたたみ・削除つき）とその中身を、1つの塊として描画する。"""
    collapsed = group_name in st.session_state["collapsed_groups"]

    with st.container(key=f"ln-group-{index}"):
        toggle_col, heading_col, delete_col = st.columns(
            [0.35, 9, 0.45], vertical_alignment="center"
        )
        toggle_col.button(
            ":material/chevron_right:" if collapsed else ":material/expand_more:",
            key=f"group_toggle_{group_name}",
            help="このグループを開く / 閉じる",
            on_click=toggle_group,
            args=(group_name,),
        )
        with heading_col:
            render_group_bar(group_name, len(group_all))
        delete_col.button(
            ":material/delete_sweep:",
            key=f"group_delete_{group_name}",
            help=f"「{group_name}」の{len(group_all)}件をまとめて削除します",
            on_click=open_bulk_delete_dialog,
            args=([item.id for item in group_all], f"グループ「{group_name}」の "),
        )

        if not collapsed:
            render_items(repository, group_items)


def render_body(repository: ListRepository, items: list[SharePointList]) -> None:
    filtered = filter_lists(
        items,
        query=st.session_state["search_query"],
        favorites_only=st.session_state["favorites_only"],
        groups=st.session_state["selected_groups"],
        tags=st.session_state["selected_tags"],
        environments=st.session_state["selected_environments"],
    )

    render_sidebar(repository, items, total=len(items), shown=len(filtered))

    if not items:
        render_note(
            "まだリストが登録されていません。"
            "右上の「＋ 登録」またはBookmarkletの出力を「貼り付け取込」から登録してください。"
        )
        return

    if not filtered:
        render_note("条件に一致するリストがありません。検索語やフィルターを見直してください。", "warn")
        return

    if st.session_state["view_mode"] == VIEW_TABLE:
        render_table_view(repository, filtered)
        return

    limit = st.session_state["visible_count"]

    if st.session_state["group_view"]:
        groups = group_by_group_name(filtered)
        collapsed_names = set(st.session_state["collapsed_groups"])

        # 折りたたみ中のグループは表示件数に数えない（畳めばその分だけ他を出せる）。
        shown_groups: list[tuple[str, list[SharePointList]]] = []
        shown_count = 0
        for name, group_items in groups:
            if shown_count >= limit and shown_groups:
                break
            shown_groups.append((name, group_items))
            if name not in collapsed_names:
                shown_count += len(group_items)

        expand_col, collapse_col, _ = st.columns([0.5, 0.5, 9])
        all_names = [name for name, _ in groups]
        expand_col.button(
            ":material/unfold_more:",
            key="expand_all_groups",
            help="すべてのグループを開く",
            on_click=set_all_groups_collapsed,
            args=(all_names, False),
        )
        collapse_col.button(
            ":material/unfold_less:",
            key="collapse_all_groups",
            help="すべてのグループを閉じる",
            on_click=set_all_groups_collapsed,
            args=(all_names, True),
        )

        for index, (name, group_items) in enumerate(shown_groups):
            render_group_section(repository, index, name, group_items, group_items)

        render_pager(len(shown_groups), len(groups), unit="グループ")
        return

    visible = filtered[:limit]
    favorites = [item for item in visible if item.favorite]
    others = [item for item in visible if not item.favorite]

    if favorites:
        render_section_heading("★ お気に入り", len(favorites))
        render_items(repository, favorites)
    if others:
        render_section_heading("すべてのリスト" if favorites else "リスト", len(others))
        render_items(repository, others)

    render_pager(len(visible), len(filtered))


def show_more() -> None:
    st.session_state["visible_count"] = st.session_state["visible_count"] + PAGE_SIZE


def show_all(total: int) -> None:
    st.session_state["visible_count"] = total


def render_pager(shown: int, total: int, unit: str = "件") -> None:
    """未表示分があれば「さらに表示」を出す。"""
    if shown >= total:
        return
    st.markdown("---")
    render_note(
        f"{total}{unit}のうち{shown}{unit}を表示しています（動作を軽く保つため表示量を制限しています）。"
    )
    more_col, all_col, _ = st.columns([1.2, 1.2, 4])
    more_col.button(
        f"さらに表示",
        use_container_width=True,
        key="show_more",
        on_click=show_more,
    )
    all_col.button(
        f"すべて表示（{total}{unit}）",
        use_container_width=True,
        key="show_all",
        on_click=show_all,
        args=(total,),
    )


def render_dialogs(repository: ListRepository) -> None:
    dialog = st.session_state.get("dialog")
    if dialog == "create":
        create_dialog(repository)
    elif dialog == "edit":
        edit_dialog(repository)
    elif dialog == "delete":
        delete_dialog(repository)
    elif dialog == "bulk_delete":
        bulk_delete_dialog(repository)
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

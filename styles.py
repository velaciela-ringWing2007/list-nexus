"""サイバーパンク風ダークテーマのCSSと、HTML片の生成.

CSSは機能ロジックから分離し、このモジュールに閉じ込める。
HTMLへユーザー入力を出力する場合は、必ず escape_html() を通す。
"""

from __future__ import annotations

import html
from typing import Iterable

import streamlit as st

from constants import HIGHLIGHT_ENVIRONMENTS, environment_label

# 配色（可読性を最優先し、彩度の高い色は輪郭と強調にのみ使う）
COLOR_BACKGROUND = "#070b16"
COLOR_PANEL = "#0e1526"
COLOR_PANEL_ALT = "#131c31"
COLOR_ACCENT = "#22d3ee"
COLOR_ACCENT_SUB = "#f472d0"
COLOR_TEXT = "#dbe6ff"
COLOR_MUTED = "#8fa0c0"
COLOR_WARN = "#fbbf24"
COLOR_DANGER = "#f87171"

_CSS = f"""
<style>
:root {{
    --ln-bg: {COLOR_BACKGROUND};
    --ln-panel: {COLOR_PANEL};
    --ln-panel-alt: {COLOR_PANEL_ALT};
    --ln-accent: {COLOR_ACCENT};
    --ln-accent-sub: {COLOR_ACCENT_SUB};
    --ln-text: {COLOR_TEXT};
    --ln-muted: {COLOR_MUTED};
    --ln-warn: {COLOR_WARN};
    --ln-danger: {COLOR_DANGER};
    --ln-border: rgba(34, 211, 238, 0.28);
}}

/* ---------- 全体 ---------- */
[data-testid="stAppViewContainer"] {{
    background-color: var(--ln-bg);
    background-image:
        linear-gradient(rgba(34, 211, 238, 0.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(34, 211, 238, 0.05) 1px, transparent 1px);
    background-size: 44px 44px;
    color: var(--ln-text);
}}

[data-testid="stHeader"] {{
    background: transparent;
}}

[data-testid="stSidebar"] {{
    background-color: var(--ln-panel);
    border-right: 1px solid var(--ln-border);
}}

[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3,
[data-testid="stAppViewContainer"] h4 {{
    color: var(--ln-text);
    letter-spacing: 0.04em;
}}

/* ---------- アプリタイトル ---------- */
.ln-brand {{
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    margin: 0 0 0.2rem 0;
}}
.ln-brand__name {{
    font-size: 1.9rem;
    font-weight: 800;
    letter-spacing: 0.18em;
    color: var(--ln-accent);
    text-shadow: 0 0 12px rgba(34, 211, 238, 0.45);
}}
.ln-brand__sub {{
    font-size: 0.8rem;
    color: var(--ln-muted);
    letter-spacing: 0.16em;
}}
.ln-rule {{
    height: 1px;
    margin: 0.4rem 0 1.1rem 0;
    background: linear-gradient(90deg, var(--ln-accent), rgba(244, 114, 208, 0.55), transparent);
}}

/* ---------- セクション見出し ---------- */
.ln-section {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 1.1rem 0 0.5rem 0;
    font-size: 1.02rem;
    font-weight: 700;
    color: var(--ln-accent);
    letter-spacing: 0.08em;
}}
.ln-section__count {{
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--ln-muted);
    letter-spacing: 0.04em;
}}

/* ---------- タイル ---------- */
[class*="st-key-ln-tile-"] {{
    background: linear-gradient(160deg, var(--ln-panel) 0%, var(--ln-panel-alt) 100%);
    border: 1px solid var(--ln-border) !important;
    border-radius: 10px;
    padding: 0.35rem 0.15rem;
    height: 100%;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}}
[class*="st-key-ln-tile-"]:hover {{
    border-color: var(--ln-accent) !important;
    box-shadow: 0 0 14px rgba(34, 211, 238, 0.22);
}}

/* リスト名は省略せず全文表示する（text-overflow: ellipsis は使わない） */
.ln-title {{
    font-size: 1.02rem;
    font-weight: 700;
    line-height: 1.45;
    color: var(--ln-text);
    word-break: break-word;
    overflow-wrap: anywhere;
    white-space: normal;
    margin: 0 0 0.35rem 0;
}}
.ln-meta {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    margin-bottom: 0.4rem;
}}
.ln-desc {{
    font-size: 0.84rem;
    line-height: 1.5;
    color: var(--ln-muted);
    word-break: break-word;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
    margin: 0 0 0.4rem 0;
}}
.ln-url {{
    font-size: 0.72rem;
    color: rgba(143, 160, 192, 0.75);
    word-break: break-all;
    margin: 0 0 0.3rem 0;
}}

/* ---------- チップ ---------- */
.ln-chip {{
    display: inline-block;
    padding: 0.08rem 0.5rem;
    border-radius: 999px;
    font-size: 0.72rem;
    line-height: 1.6;
    border: 1px solid rgba(143, 160, 192, 0.45);
    color: var(--ln-muted);
    background: rgba(143, 160, 192, 0.08);
    white-space: normal;
    word-break: break-word;
}}
.ln-chip--site {{
    border-color: rgba(34, 211, 238, 0.5);
    color: var(--ln-accent);
    background: rgba(34, 211, 238, 0.08);
}}
.ln-chip--group {{
    border-color: rgba(244, 114, 208, 0.5);
    color: var(--ln-accent-sub);
    background: rgba(244, 114, 208, 0.08);
}}
.ln-chip--tag {{
    border-color: rgba(219, 230, 255, 0.35);
    color: var(--ln-text);
    background: rgba(219, 230, 255, 0.06);
}}
.ln-chip--env {{
    border-color: rgba(143, 160, 192, 0.5);
}}
.ln-chip--env-highlight {{
    border-color: var(--ln-warn);
    color: #10131f;
    background: var(--ln-warn);
    font-weight: 700;
}}
.ln-chip--fav {{
    border-color: var(--ln-warn);
    color: var(--ln-warn);
    background: rgba(251, 191, 36, 0.1);
}}

/* ---------- ボタン ---------- */
.stButton > button,
.stDownloadButton > button,
[data-testid="stLinkButton"] a {{
    border: 1px solid var(--ln-border);
    background: rgba(34, 211, 238, 0.07);
    color: var(--ln-text);
    border-radius: 6px;
    font-size: 0.82rem;
    transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}}
.stButton > button:hover,
.stDownloadButton > button:hover,
[data-testid="stLinkButton"] a:hover {{
    border-color: var(--ln-accent);
    background: rgba(34, 211, 238, 0.16);
    color: #ffffff;
    box-shadow: 0 0 10px rgba(34, 211, 238, 0.28);
}}
.stButton > button[kind="primary"] {{
    border-color: var(--ln-accent);
    background: rgba(34, 211, 238, 0.2);
    font-weight: 700;
}}
/* 無効なボタン（URL未登録など）は淡く表示する */
.stButton > button:disabled,
[data-testid="stLinkButton"] a[disabled] {{
    opacity: 0.4;
    box-shadow: none;
}}

/* ---------- 入力系 ---------- */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input {{
    background-color: rgba(7, 11, 22, 0.85);
    color: var(--ln-text);
    border: 1px solid var(--ln-border);
}}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {{
    border-color: var(--ln-accent);
    box-shadow: 0 0 8px rgba(34, 211, 238, 0.3);
}}

/* ---------- タイル内リンク ----------
   st.link_button はウィジェット扱いになり、件数が増えると再描画が重くなる。
   タイルのリンクは素のアンカーで描画する（SPEC 15.5 の優先順位2）。 */
.ln-links {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin: 0.2rem 0 0.45rem 0;
}}
.ln-links a {{
    flex: 1 1 auto;
    text-align: center;
    padding: 0.25rem 0.7rem;
    border: 1px solid var(--ln-border);
    border-radius: 6px;
    background: rgba(34, 211, 238, 0.07);
    color: var(--ln-text) !important;
    font-size: 0.82rem;
    text-decoration: none;
    transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}}
.ln-links a:hover {{
    border-color: var(--ln-accent);
    background: rgba(34, 211, 238, 0.16);
    color: #ffffff !important;
    box-shadow: 0 0 10px rgba(34, 211, 238, 0.28);
}}
.ln-links a.ln-links__primary {{
    border-color: rgba(34, 211, 238, 0.55);
    font-weight: 700;
}}

/* ---------- 通知 ---------- */
.ln-note {{
    border-left: 3px solid var(--ln-accent);
    background: rgba(34, 211, 238, 0.07);
    padding: 0.5rem 0.75rem;
    border-radius: 4px;
    font-size: 0.85rem;
    color: var(--ln-text);
}}
.ln-note--warn {{
    border-left-color: var(--ln-warn);
    background: rgba(251, 191, 36, 0.09);
}}
.ln-note--error {{
    border-left-color: var(--ln-danger);
    background: rgba(248, 113, 113, 0.09);
}}

/* ---------- 狭い画面 ---------- */
@media (max-width: 640px) {{
    .ln-brand__name {{ font-size: 1.4rem; }}
    .ln-title {{ font-size: 0.96rem; }}
}}
</style>
"""


def apply_styles() -> None:
    """アプリ全体のCSSを適用する。CSSは固定文字列のみ。"""
    st.markdown(_CSS, unsafe_allow_html=True)


def escape_html(value: str | None) -> str:
    """HTMLへ埋め込む前にユーザー入力をエスケープする。"""
    return html.escape(str(value or ""), quote=True)


def render_brand() -> None:
    """アプリタイトルを描画する。"""
    st.markdown(
        '<div class="ln-brand">'
        '<span class="ln-brand__name">LIST NEXUS</span>'
        '<span class="ln-brand__sub">SHAREPOINT LIST LAUNCHER</span>'
        "</div>"
        '<div class="ln-rule"></div>',
        unsafe_allow_html=True,
    )


def render_section_heading(title: str, count: int | None = None) -> None:
    """セクション見出しを描画する。タイトルはエスケープする。"""
    suffix = (
        f'<span class="ln-section__count">{count}件</span>' if count is not None else ""
    )
    st.markdown(
        f'<div class="ln-section">{escape_html(title)}{suffix}</div>',
        unsafe_allow_html=True,
    )


def chip(text: str, variant: str = "") -> str:
    """チップのHTML片を返す。text はエスケープする。"""
    class_name = "ln-chip" + (f" ln-chip--{variant}" if variant else "")
    return f'<span class="{class_name}">{escape_html(text)}</span>'


def environment_chip(environment: str) -> str:
    """環境チップのHTML片を返す。本番は強調表示する。"""
    if not environment:
        return ""
    variant = "env-highlight" if environment in HIGHLIGHT_ENVIRONMENTS else "env"
    return chip(environment_label(environment), variant)


def render_meta_row(chips: Iterable[str]) -> None:
    """チップの並びを描画する。空要素は無視する。"""
    items = [item for item in chips if item]
    if not items:
        return
    st.markdown(f'<div class="ln-meta">{"".join(items)}</div>', unsafe_allow_html=True)


def render_title(name: str) -> None:
    """リスト名を全文表示する。"""
    st.markdown(f'<div class="ln-title">{escape_html(name)}</div>', unsafe_allow_html=True)


def render_description(description: str) -> None:
    """説明文を描画する。"""
    if not description.strip():
        return
    st.markdown(
        f'<div class="ln-desc">{escape_html(description)}</div>', unsafe_allow_html=True
    )


def render_url_hint(url: str) -> None:
    """URLを補助表示する。"""
    if not url:
        return
    st.markdown(f'<div class="ln-url">{escape_html(url)}</div>', unsafe_allow_html=True)


def render_link_row(links: Iterable[tuple[str, str]], *, primary_first: bool = True) -> None:
    """(ラベル, URL) の並びを新しいタブで開くリンクとして描画する。

    ラベルとURLは必ずエスケープする。URLは呼び出し前に http/https 検証済みであること。
    """
    items: list[str] = []
    for index, (label, url) in enumerate([link for link in links if link[1]]):
        css_class = "ln-links__primary" if primary_first and index == 0 else ""
        items.append(
            f'<a class="{css_class}" href="{escape_html(url)}" '
            f'target="_blank" rel="noopener noreferrer">{escape_html(label)}</a>'
        )
    if not items:
        return
    st.markdown(f'<div class="ln-links">{"".join(items)}</div>', unsafe_allow_html=True)


def render_note(message: str, level: str = "info") -> None:
    """簡易メッセージを描画する。message はエスケープする。"""
    modifier = {"warn": " ln-note--warn", "error": " ln-note--error"}.get(level, "")
    st.markdown(
        f'<div class="ln-note{modifier}">{escape_html(message)}</div>',
        unsafe_allow_html=True,
    )

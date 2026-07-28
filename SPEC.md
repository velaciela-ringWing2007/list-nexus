# LIST NEXUS 開発仕様書

## 1. プロジェクト概要

### 1.1 プロジェクト名

**LIST NEXUS**

SharePoint Listsを大量に利用しているユーザー向けの、ローカル専用リンク管理・ランチャーアプリケーション。

SharePointのお気に入り機能では管理しきれない多数のリストを、以下の情報で整理・検索・起動できるようにする。

* リスト名
* 一覧画面URL
* 新規作成画面URL
* 設定画面URL
* グループ
* タグ
* サイト名
* 環境区分
* お気に入り
* 説明

本アプリケーションはSharePointのデータを直接編集するものではない。

各SharePoint Listへのリンクを管理し、一覧画面、新規作成画面、設定画面などをブラウザで開くためのローカルポータルとして動作する。

---

## 2. 初期作成ディレクトリ

プロジェクトのルートディレクトリ名は以下とする。

```text
list-nexus
```

Windows上での想定配置例：

```text
C:\Users\<ユーザー名>\apps\list-nexus
```

または：

```text
C:\dev\list-nexus
```

初期ディレクトリ構成：

```text
list-nexus/
├─ app.py
├─ database.py
├─ models.py
├─ repositories.py
├─ import_parser.py
├─ url_utils.py
├─ styles.py
├─ constants.py
├─ requirements.txt
├─ README.md
├─ SPEC.md
├─ .gitignore
├─ start.bat
├─ setup.bat
├─ assets/
│  └─ .gitkeep
├─ data/
│  └─ .gitkeep
├─ scripts/
│  └─ bookmarklets.md
└─ tests/
   ├─ __init__.py
   ├─ test_import_parser.py
   ├─ test_url_utils.py
   └─ test_repositories.py
```

SQLiteファイルは以下に作成する。

```text
data/list_nexus.sqlite3
```

SQLiteファイルはGit管理対象外とする。

---

## 3. 技術構成

### 3.1 使用技術

* Python 3.12以上
* Streamlit
* SQLite
* Python標準ライブラリ
* pytest

外部依存は可能な限り少なくする。

### 3.2 必須パッケージ

`requirements.txt`：

```text
streamlit
pytest
```

必要性が明確でないパッケージは追加しない。

ORMは使用せず、Python標準ライブラリの `sqlite3` を使用する。

### 3.3 対象環境

主な対象環境：

* Windows 11
* Microsoft Edge
* ローカルPC
* 単一ユーザー利用
* `127.0.0.1` のみで待ち受ける

外部ネットワークからアクセス可能な状態にはしない。

---

## 4. 基本方針

### 4.1 アプリケーションの責務

本アプリケーションは以下の機能のみを担当する。

* SharePoint Listのリンク情報管理
* リスト情報の検索
* グルーピング
* タグ付け
* お気に入り管理
* SharePointページの起動
* JSONインポート
* JSONエクスポート
* Bookmarklet用データの受け入れ

### 4.2 対象外

初期バージョンでは以下を実装しない。

* Microsoft Graph API連携
* Microsoft Entra ID認証
* SharePoint内のリスト自動取得
* SharePoint Listのアイテム参照
* SharePoint Listのアイテム更新
* 複数ユーザー対応
* クラウド同期
* Electron化
* Docker化
* npmおよびNode.jsの使用

---

## 5. UIコンセプト

### 5.1 デザイン

サイバーパンク風のダークテーマとする。

ただし、業務利用に必要な可読性を最優先する。

基本配色：

* 背景：黒に近い濃紺
* パネル：濃い青黒
* メインアクセント：シアン
* サブアクセント：マゼンタ
* 通常文字：白に近い薄青
* 補助文字：グレー
* 警告：黄またはオレンジ
* 削除：赤系

装飾要素：

* 薄いグリッド背景
* シアン系の境界線
* 軽い発光表現
* ホバー時の発光
* タイル型UI

過度なアニメーションは使用しない。

### 5.2 レイアウト

画面は以下の構成とする。

```text
┌────────────────────────────────────────────────────────────┐
│ LIST NEXUS                 検索欄      登録  インポート等 │
├────────────────┬───────────────────────────────────────────┤
│ サイドバー     │ メイン領域                                │
│                │                                           │
│ すべて         │ お気に入り                                │
│ お気に入り     │ ┌────────────┐ ┌────────────┐             │
│                │ │ リスト名   │ │ リスト名   │             │
│ グループ       │ │ 全文表示   │ │ 全文表示   │             │
│                │ │            │ │            │             │
│ タグ           │ │ 各種ボタン │ │ 各種ボタン │             │
│                │ └────────────┘ └────────────┘             │
│ 環境           │                                           │
└────────────────┴───────────────────────────────────────────┘
```

### 5.3 タイル表示

1件のSharePoint Listを1つのタイルとして表示する。

タイル内の必須表示項目：

* お気に入り状態
* リスト名
* サイト名
* グループ名
* 環境
* タグ
* 説明
* 一覧を開くボタン
* 新規作成ボタン
* その他メニューまたは編集ボタン

リスト名は途中で省略しない。

長いリスト名は複数行で全文表示する。

CSSの `text-overflow: ellipsis` は使用しない。

タイルの高さは内容に応じて増えてよい。

---

## 6. 機能要件

## 6.1 リスト一覧

登録済みのSharePoint Listをタイル形式で表示する。

初期表示順：

1. お気に入り
2. `sort_order`
3. リスト名

グループ表示を有効にしている場合：

1. グループ単位でセクション分け
2. 各グループ内でお気に入り優先
3. `sort_order`
4. リスト名

未分類のリストは以下のグループに表示する。

```text
未分類
```

## 6.2 検索

画面上部に検索入力欄を設置する。

検索対象：

* リスト名
* サイト名
* グループ名
* タグ
* 説明
* 一覧URL

検索は大文字・小文字を区別しない。

日本語を含む部分一致検索とする。

入力内容に応じて表示を即時絞り込みする。

## 6.3 フィルター

サイドバーから以下で絞り込めるようにする。

* すべて
* お気に入りのみ
* グループ
* タグ
* 環境

複数条件の組み合わせに対応する。

例：

```text
グループ：開発
タグ：障害
環境：本番
お気に入りのみ：ON
```

## 6.4 新規登録

「登録」ボタンから登録ダイアログを開く。

登録可能項目：

* リスト名
* 一覧URL
* 新規作成URL
* 設定画面URL
* サイト名
* グループ名
* タグ
* 環境
* 説明
* お気に入り
* 表示順

必須項目：

* リスト名
* 一覧URL

一覧URLはデータベース内で一意とする。

重複URLを登録しようとした場合は、既存データを案内し、登録しない。

## 6.5 編集

各タイルの編集ボタンから編集ダイアログを開く。

すべての登録項目を編集可能とする。

更新日時を自動更新する。

## 6.6 削除

各タイルから削除可能とする。

削除時は確認画面を表示する。

確認文にはリスト名を含める。

例：

```text
「障害管理リスト」を削除しますか？
```

削除は物理削除でよい。

初期バージョンではゴミ箱機能は実装しない。

## 6.7 お気に入り

各タイルからお気に入り状態を切り替えられるようにする。

お気に入り状態は即座にSQLiteへ保存する。

## 6.8 SharePointページを開く

各タイルには以下のリンクボタンを表示する。

### 一覧を開く

`list_url` を新しいタブで開く。

### 新規作成

`new_item_url` が登録されている場合のみ有効にする。

新しいタブで開く。

### 設定

`settings_url` が登録されている場合のみ表示する。

新しいタブで開く。

URLの起動は可能な限りStreamlitの `st.link_button` または通常のHTMLリンクを使用する。

独自JavaScriptによる `window.open` は必要な場合に限る。

---

## 7. インポート機能

## 7.1 貼り付けインポート

ユーザーがテキストを貼り付けて登録情報を取り込めるようにする。

受け付ける形式：

### JSONオブジェクト

```json
{
  "name": "障害管理",
  "listUrl": "https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx",
  "newItemUrl": "https://example.sharepoint.com/sites/dev/Lists/Issues/NewForm.aspx"
}
```

### snake_case JSON

```json
{
  "name": "障害管理",
  "list_url": "https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx",
  "new_item_url": "https://example.sharepoint.com/sites/dev/Lists/Issues/NewForm.aspx"
}
```

### Markdownリンク

```markdown
[障害管理](https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx)
```

### HTMLリンク

```html
<a href="https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx">
  障害管理
</a>
```

### 名前とURL

```text
障害管理
https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx
```

### URLのみ

```text
https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx
```

URLのみの場合、名前はURLから推測せず、ユーザーに入力させる。

## 7.2 複数件インポート

JSON配列による複数件取り込みに対応する。

```json
[
  {
    "name": "障害管理",
    "listUrl": "https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx"
  },
  {
    "name": "端末管理",
    "listUrl": "https://example.sharepoint.com/sites/dev/Lists/Devices/AllItems.aspx"
  }
]
```

複数の「名前＋URL」形式にも可能であれば対応する。

```text
障害管理
https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx

端末管理
https://example.sharepoint.com/sites/dev/Lists/Devices/AllItems.aspx
```

## 7.3 インポート確認

インポートデータを直接保存しない。

解析後にプレビュー画面を表示する。

プレビューで以下を確認・修正可能にする。

* リスト名
* 一覧URL
* 新規作成URL
* グループ
* タグ
* 重複状態
* エラー

ユーザーが確定したデータのみ保存する。

---

## 8. Bookmarklet

以下のBookmarkletを `scripts/bookmarklets.md` に記載する。

### 8.1 一覧ページ取得Bookmarklet

目的：

* 現在のページタイトルを取得
* 現在のURLを取得
* JSONに変換
* クリップボードへコピー

出力形式：

```json
{
  "name": "障害管理",
  "listUrl": "https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx",
  "sourceTitle": "障害管理 - Microsoft Lists",
  "capturedAt": "2026-07-27T12:00:00.000Z"
}
```

Bookmarklet例：

```javascript
javascript:(async()=>{const data={name:document.title.replace(/\s*-\s*Microsoft Lists.*$/i,'').replace(/\s*-\s*SharePoint.*$/i,'').trim(),listUrl:location.href,sourceTitle:document.title,capturedAt:new Date().toISOString()};const text=JSON.stringify(data,null,2);try{await navigator.clipboard.writeText(text);alert('リスト情報をコピーしました\n\n'+data.name);}catch(e){prompt('コピーしてください',text);}})();
```

### 8.2 新規作成ページ取得Bookmarklet

目的：

* 現在開いている新規作成ページURLを取得
* JSONとしてコピー

出力形式：

```json
{
  "action": "newItem",
  "name": "障害管理",
  "newItemUrl": "https://example.sharepoint.com/sites/dev/Lists/Issues/NewForm.aspx",
  "capturedAt": "2026-07-27T12:00:00.000Z"
}
```

Bookmarklet例：

```javascript
javascript:(async()=>{const data={action:"newItem",name:document.title.replace(/\s*-\s*Microsoft Lists.*$/i,'').replace(/\s*-\s*SharePoint.*$/i,'').trim(),newItemUrl:location.href,capturedAt:new Date().toISOString()};const text=JSON.stringify(data,null,2);try{await navigator.clipboard.writeText(text);alert('新規作成URLをコピーしました');}catch(e){prompt('コピーしてください',text);}})();
```

---

## 9. URL補助機能

一覧URLから新規作成URL候補を生成する。

対象例：

```text
/AllItems.aspx
```

変換例：

```text
/AllItems.aspx
↓
/NewForm.aspx
```

以下のような既知の表示ページも候補対象とする。

```text
/AllItems.aspx
/MyItems.aspx
/ByAuthor.aspx
```

ただし、以下の場合があるため、生成結果は必ず編集可能にする。

* Power Appsカスタムフォーム
* 特殊なSharePoint List
* クエリ文字列付きURL
* 独自ビュー
* URL構成が標準と異なるリスト

自動生成したURLを確定値として扱わない。

候補としてフォームへ入力するだけにする。

URL生成時はクエリ文字列とフラグメントを原則除去する。

---

## 10. データモデル

## 10.1 listsテーブル

```sql
CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    list_url TEXT NOT NULL UNIQUE,
    new_item_url TEXT,
    settings_url TEXT,
    site_name TEXT NOT NULL DEFAULT '',
    group_name TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    environment TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    favorite INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    open_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### カラム仕様

#### id

* 整数
* 主キー
* 自動採番

#### name

* リスト表示名
* 必須
* 空文字不可

#### list_url

* SharePoint List一覧URL
* 必須
* UNIQUE制約
* `http://` または `https://` のみ許可

#### new_item_url

* 新規作成画面URL
* 任意

#### settings_url

* リスト設定画面URL
* 任意

#### site_name

* SharePointサイト名
* 任意

#### group_name

* ユーザー定義のグループ名
* 任意

#### tags

* JSON配列文字列
* 例：`["障害", "本番"]`

#### environment

想定値：

```text
production
staging
development
test
personal
other
```

UI表示は日本語でもよい。

```text
本番
検証
開発
テスト
個人
その他
```

未設定も許可する。

#### description

* 自由記述
* 任意

#### favorite

* 0または1

#### sort_order

* 整数
* 小さい値を先に表示

#### open_count

* 一覧ページを開いた回数
* 初期バージョンで正確に取得できない場合は、アプリ内の専用操作時のみ加算する
* 実装が不安定になる場合は画面表示しなくてよい

#### created_at

* ISO 8601形式
* UTCまたはローカル時刻のどちらかに統一する

#### updated_at

* ISO 8601形式
* 更新ごとに変更する

---

## 11. Pythonモデル

可能であれば `dataclasses.dataclass` を使用する。

例：

```python
from dataclasses import dataclass, field


@dataclass(slots=True)
class SharePointList:
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
```

---

## 12. データアクセス方針

SQLをUIコードへ直接書かない。

以下の責務に分離する。

### database.py

* SQLite接続
* DBファイル作成
* テーブル初期化
* トランザクション補助
* SQLite設定

推奨設定：

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
```

### repositories.py

* 全件取得
* ID指定取得
* URL指定取得
* 新規登録
* 更新
* 削除
* お気に入り更新
* グループ一覧取得
* タグ一覧取得

### models.py

* データモデル
* DB行との変換

UI層からSQLite接続を直接扱わない。

---

## 13. 入力検証

登録・更新時に以下を検証する。

### リスト名

* 前後の空白を除去
* 空文字不可
* 最大文字数は200文字程度

### URL

* 前後の空白を除去
* 一覧URLは必須
* `http` または `https` のみ
* 一覧URLは重複不可
* JavaScript URLは拒否
* `data:` URLは拒否
* 改行を含むURLは拒否

### タグ

* カンマ区切りまたは配列入力
* 前後空白を削除
* 空タグを削除
* 重複タグを削除
* 入力順を維持する
* タグ1件の最大文字数は50文字程度

### 表示順

* 整数
* 未入力時は0

---

## 14. JSONエクスポート

登録データをJSONとしてダウンロード可能にする。

ファイル名例：

```text
list-nexus-backup-20260727-153000.json
```

形式：

```json
{
  "schemaVersion": 1,
  "exportedAt": "2026-07-27T15:30:00+09:00",
  "lists": [
    {
      "name": "障害管理",
      "listUrl": "https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx",
      "newItemUrl": "https://example.sharepoint.com/sites/dev/Lists/Issues/NewForm.aspx",
      "settingsUrl": "",
      "siteName": "開発部",
      "group": "開発",
      "tags": [
        "障害",
        "本番"
      ],
      "environment": "production",
      "description": "",
      "favorite": true,
      "sortOrder": 0
    }
  ]
}
```

内部DBの `id` はエクスポートしなくてよい。

`created_at` と `updated_at` は任意。

## 14.1 JSONインポート

エクスポート形式のJSONを再取り込みできるようにする。

重複時の動作は選択可能にする。

* スキップ
* 既存を更新
* エラーとして扱う

初期選択は「スキップ」とする。

---

## 15. Streamlit実装方針

### 15.1 ページ設定

```python
st.set_page_config(
    page_title="LIST NEXUS",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)
```

### 15.2 Session State

`st.session_state` は以下の一時状態にのみ使用する。

* 編集対象ID
* 削除対象ID
* インポートプレビュー
* 一時的なフィルター状態
* ダイアログ状態

永続データは必ずSQLiteへ保存する。

### 15.3 キャッシュ

データベース接続そのものを長期間キャッシュしない。

取得データをキャッシュする場合は、登録・更新・削除後に確実に無効化する。

初期バージョンでは、件数が少ないためキャッシュを使用しなくてもよい。

### 15.4 ダイアログ

利用可能なStreamlitバージョンでは `st.dialog` を使用する。

対象：

* 新規登録
* 編集
* 削除確認
* 貼り付けインポート
* JSONインポート

ダイアログに依存しすぎて不安定になる場合は、画面内フォームへ切り替えてよい。

### 15.5 リンク

SharePoint URLは新しいタブで開く。

優先順位：

1. `st.link_button`
2. `<a target="_blank" rel="noopener noreferrer">`
3. JavaScript

---

## 16. CSS要件

`styles.py` にCSS適用処理をまとめる。

CSSは機能ロジックと分離する。

Streamlit内部DOMへ強く依存するセレクタは最小限にする。

最低限対応する要素：

* アプリ背景
* サイドバー背景
* 見出し
* タイル
* ボタン
* タグ表示
* お気に入り
* 本番環境表示
* 警告
* エラー

タイルのリスト名は全文表示する。

スマートフォン対応は必須ではないが、狭い画面でも致命的に崩れないようにする。

---

## 17. Windows用セットアップ

## 17.1 setup.bat

以下を自動実行する。

1. Pythonの存在確認
2. `.venv` 作成
3. pip更新
4. `requirements.txt` インストール
5. DB初期化確認
6. 完了メッセージ

想定コマンド：

```bat
@echo off
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo Pythonが見つかりません。
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
)

call ".venv\Scripts\activate.bat"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo セットアップが完了しました。
pause
```

## 17.2 start.bat

以下を実行する。

* プロジェクトルートへ移動
* `.venv` のPythonを使用
* Streamlit起動
* `127.0.0.1` で待ち受け
* ポート8501を使用
* ブラウザ起動

例：

```bat
@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Python仮想環境がありません。
    echo setup.batを先に実行してください。
    pause
    exit /b 1
)

start "" http://127.0.0.1:8501

".venv\Scripts\python.exe" -m streamlit run app.py ^
    --server.address 127.0.0.1 ^
    --server.port 8501 ^
    --browser.gatherUsageStats false
```

---

## 18. Git管理

プロジェクト作成時にGitリポジトリを初期化する。

```bash
git init
```

初回コミットを必ず作成する。

コミット例：

```bash
git add .
git commit -m "Initial project setup"
```

以後、意味のある単位でコミットする。

推奨コミット単位：

```text
Initial project setup
Add SQLite repository layer
Add list registration and editing
Add tile dashboard and filtering
Add import parser
Add JSON backup and restore
Add cyberpunk theme
Add tests and documentation
```

コミットメッセージは英語または日本語のどちらでもよいが、プロジェクト内で統一する。

### 18.1 .gitignore

最低限以下を含める。

```gitignore
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
.pytest_cache/
.coverage
htmlcov/

# Virtual environment
.venv/
venv/

# Streamlit
.streamlit/secrets.toml

# Database and local data
data/*.sqlite
data/*.sqlite3
data/*.db
data/*.db-shm
data/*.db-wal

# Backup files
*.bak
*.backup

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
desktop.ini
```

`data/.gitkeep` はGit管理する。

---

## 19. テスト要件

pytestで最低限以下をテストする。

## 19.1 import_parser

* JSONオブジェクト
* JSON配列
* camelCase
* snake_case
* Markdownリンク
* HTMLリンク
* 名前＋URL
* URLのみ
* 不正JSON
* URLなし
* 空文字
* 複数件
* 日本語名
* HTMLエスケープ

## 19.2 url_utils

* `AllItems.aspx` から `NewForm.aspx`
* `MyItems.aspx` から `NewForm.aspx`
* クエリ文字列除去
* フラグメント除去
* 大文字・小文字差
* 対応外URL
* 不正URL

## 19.3 repositories

テスト用一時SQLite DBを使用する。

* 初期化
* 登録
* 取得
* 更新
* 削除
* URL重複
* お気に入り更新
* タグJSON変換
* 日本語データ
* トランザクション

UIの自動テストは初期バージョンでは必須としない。

---

## 20. エラーハンドリング

ユーザー向け画面にPythonのスタックトレースを直接表示しない。

以下の場合に分かりやすいメッセージを表示する。

* 必須項目不足
* URL形式不正
* URL重複
* JSON解析失敗
* SQLite接続失敗
* SQLite書き込み失敗
* インポート形式不明
* バックアップファイル不正

ログには必要な情報を記録してよい。

機密情報やURL内の認証トークンを不用意にログ出力しない。

---

## 21. セキュリティ要件

* Streamlitは `127.0.0.1` のみで待ち受ける
* SharePointのユーザー名やパスワードを保存しない
* Cookieを保存しない
* Microsoft認証トークンを保存しない
* Bookmarkletから取得したHTML本文を保存しない
* URLスキームを検証する
* `javascript:` URLを拒否する
* HTML出力時はユーザー入力をエスケープする
* `unsafe_allow_html=True` を使う箇所では、ユーザー入力を直接埋め込まない

---

## 22. README要件

READMEには以下を記載する。

* LIST NEXUSの説明
* 主な機能
* 必要環境
* セットアップ方法
* 起動方法
* Bookmarklet登録方法
* データ保存場所
* JSONバックアップ方法
* Git管理方針
* テスト実行方法
* 既知の制約
* トラブルシューティング

セットアップ例：

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

テスト：

```bash
python -m pytest
```

---

## 23. 受入条件

以下をすべて満たした時点で初期バージョン完成とする。

### 基本動作

* `setup.bat` で仮想環境と依存関係を作成できる
* `start.bat` でアプリを起動できる
* ブラウザで `http://127.0.0.1:8501` が開く
* 初回起動時にSQLite DBが自動作成される

### CRUD

* 新しいリストを登録できる
* 登録済みリストを編集できる
* 登録済みリストを削除できる
* お気に入りを切り替えられる
* アプリ再起動後も登録内容が残る

### 表示

* リストがタイル形式で表示される
* リスト名が省略されず全文表示される
* グループ単位で表示できる
* タグが表示される
* サイバーパンク風のダークテーマになっている

### 検索・絞り込み

* リスト名で検索できる
* サイト名で検索できる
* タグで検索できる
* グループで絞り込める
* お気に入りのみ表示できる
* 環境で絞り込める

### リンク

* 一覧画面を新しいタブで開ける
* 新規作成画面を新しいタブで開ける
* 設定URLがある場合は設定画面を開ける
* URL未設定のボタンは無効または非表示になる

### インポート・エクスポート

* Bookmarklet形式JSONを貼り付けて登録できる
* Markdownリンクを解析できる
* 名前＋URL形式を解析できる
* JSONバックアップをダウンロードできる
* JSONバックアップを再インポートできる
* URL重複を検出できる

### 品質

* `python -m pytest` が成功する
* READMEがある
* `.gitignore` がある
* Gitリポジトリが初期化されている
* 実装内容がコミットされている
* 未コミット変更がない状態で納品する

---

## 24. 実装優先順位

### Phase 1

* プロジェクト初期化
* Git初期化
* SQLite
* データモデル
* Repository
* 基本CRUD
* タイル表示
* URL起動

### Phase 2

* 検索
* グループ
* タグ
* お気に入り
* 環境フィルター
* サイバーパンクCSS

### Phase 3

* 貼り付けインポート
* Bookmarklet
* NewForm URL候補生成
* JSONエクスポート
* JSONインポート

### Phase 4

* pytest
* エラーハンドリング
* README
* start.bat
* setup.bat
* 最終動作確認
* Gitコミット整理

---

## 25. 完成後に実行する確認コマンド

```bash
python -m pytest
```

```bash
git status
```

期待結果：

```text
nothing to commit, working tree clean
```

可能であれば以下も確認する。

```bash
git log --oneline --decorate -10
```

実装内容が複数の意味のあるコミットに分かれていること。

---

# 実装AI向けシステムプロンプト

以下をCodexまたはClaude Codeのシステムプロンプト、プロジェクト指示、もしくは最初の依頼文として使用する。

```text
あなたは経験豊富なPythonソフトウェアエンジニアです。

このプロジェクトでは、SPEC.mdに記載された「LIST NEXUS」を実装してください。

必ず以下のルールを守ってください。

【基本方針】

- PythonとStreamlitを使用してください。
- Node.js、npm、React、Electronは使用しないでください。
- データ保存にはPython標準ライブラリのsqlite3を使用してください。
- 不要な外部ライブラリを追加しないでください。
- Windows 11で動作することを前提にしてください。
- アプリは127.0.0.1のみで待ち受けるようにしてください。
- SharePointの認証情報、Cookie、アクセストークンは保存しないでください。
- SPEC.mdにない大きな仕様変更を独断で行わないでください。
- 不明点があっても、実装を停止せず、SPEC.mdの目的に沿った安全で単純な判断をしてください。
- 判断した内容はREADME.mdまたはコードコメントへ簡潔に記録してください。

【コード品質】

- UI、データアクセス、入力解析、URL処理を適切に分離してください。
- app.pyへすべての処理を詰め込まないでください。
- 型ヒントを使用してください。
- 関数とクラスには責務が分かる名前を付けてください。
- 例外を握りつぶさないでください。
- ユーザー入力を検証してください。
- ユーザー入力をunsafe_allow_htmlへ直接埋め込まないでください。
- Pythonのスタックトレースを通常の画面へ直接表示しないでください。
- コードを必要以上に複雑化しないでください。
- 将来必要になるかもしれないという理由だけで抽象化を増やさないでください。

【テスト】

- pytestを使用してください。
- import_parser.py、url_utils.py、repositories.pyの主要処理をテストしてください。
- 実装後に必ず `python -m pytest` を実行してください。
- テスト失敗が残った状態で完了としないでください。
- テストを通すためにテスト自体を不当に弱めないでください。

【Git運用】

- 作業開始時にGitリポジトリであることを確認してください。
- Gitリポジトリでなければ `git init` を実行してください。
- .gitignoreを適切に作成してください。
- .venv、SQLiteデータベース、キャッシュ、IDE設定をコミットしないでください。
- 実装は意味のある単位に分けてコミットしてください。
- 大量の変更を最後に1コミットへまとめないでください。
- 各フェーズの完了時にコミットしてください。
- コミットメッセージは内容が分かるものにしてください。
- 作業完了時に必ず `git status` を確認してください。
- 作業完了時は原則として未コミット変更がない状態にしてください。
- 作業完了時にコミット履歴を確認してください。
- ユーザーから明示的に禁止されない限り、実装した変更は必ずコミットしてください。
- `git reset --hard`、`git clean -fd`、既存履歴の書き換えなど、破壊的なGit操作は行わないでください。
- 既存のユーザー変更を勝手に破棄しないでください。

【実装手順】

以下の順で進めてください。

1. SPEC.mdと既存ファイルを確認する
2. Git状態を確認する
3. プロジェクト構成を作る
4. SQLite初期化を実装する
5. モデルとRepositoryを実装する
6. CRUD UIを実装する
7. タイル表示、検索、グループ、タグ、お気に入りを実装する
8. 貼り付けインポートを実装する
9. JSONバックアップと復元を実装する
10. サイバーパンク風CSSを実装する
11. setup.batとstart.batを作る
12. pytestを作成して実行する
13. README.mdを完成させる
14. 実際にアプリを起動して重大な例外がないか確認する
15. Gitへコミットする
16. git statusがクリーンであることを確認する

【完了報告】

完了時には以下を報告してください。

- 実装した機能
- 作成または変更した主要ファイル
- テスト結果
- アプリの起動方法
- データベースの保存場所
- Bookmarkletの保存場所
- Gitコミット一覧
- 未実装または既知の制約
- `git status` の状態

作業途中で問題が発生した場合は、問題を隠さず報告してください。
動作未確認の内容を、確認済みであるかのように報告しないでください。
```

---

# Codex／Claude Codeへの最初の依頼文

```text
このディレクトリにあるSPEC.mdを読み、仕様に従ってLIST NEXUSを実装してください。

Python、Streamlit、SQLiteを使用してください。
Node.jsやnpmは使用しないでください。

作業開始時にGitの状態を確認し、Gitリポジトリでなければ初期化してください。
実装内容は意味のある単位で必ずコミットしてください。
作業完了時にはpytestを実行し、git statusがクリーンな状態にしてください。

途中で不明点があっても、致命的な矛盾でなければ作業を停止せず、SPEC.mdの目的に沿って単純で保守しやすい方法を選択してください。

最後に、実装内容、テスト結果、起動方法、コミット履歴、既知の制約を報告してください。
```

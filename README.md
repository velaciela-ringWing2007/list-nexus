# LIST NEXUS

SharePoint Lists を大量に使うユーザー向けの、**ローカル専用リンク管理・ランチャー**です。

SharePointのお気に入り機能では管理しきれない多数のリストを、リスト名・サイト名・グループ・タグ・環境などで整理し、
一覧画面 / 新規作成画面 / 設定画面をブラウザの新しいタブで開けます。

SharePointのデータそのものは読み書きしません。リンク情報だけをローカルのSQLiteに保存します。

## 主な機能

* SharePoint Listリンクの登録・編集・削除（タイル表示）
* 検索（リスト名 / サイト名 / グループ / タグ / 説明 / 一覧URL の部分一致・大文字小文字を区別しない）
* 絞り込み（お気に入りのみ / グループ / タグ / 環境、複数条件の組み合わせ）
* グループ単位のセクション表示（未分類は最後に表示）
* お気に入りの切り替え（即座にSQLiteへ保存）
* 一覧 / 新規作成 / 設定 画面を新しいタブで起動（未登録URLのボタンは無効表示）
* 貼り付けインポート（JSON / Markdownリンク / HTMLリンク / 名前とURL / URLのみ）
* JSONバックアップのエクスポートとインポート（重複時の動作を選択可能）
* 一覧URLからの新規作成URL候補生成（`AllItems.aspx` → `NewForm.aspx` など）
* サイバーパンク風ダークテーマ

## 必要環境

* Windows 11（他OSでも動作しますが、`.bat` はWindows専用です）
* Python 3.12以上
* Microsoft Edge などのブラウザ
* 依存パッケージは `streamlit` と `pytest` のみ（`requirements.txt`）

## セットアップ

`setup.bat` をダブルクリックすると、仮想環境の作成・依存パッケージのインストール・DB初期化まで行います。

手動で行う場合：

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## 起動方法

`start.bat` をダブルクリックします。

* `http://127.0.0.1:8501` でブラウザが開きます
* 待ち受けは `127.0.0.1` のみです（外部ネットワークからは接続できません）

## Bookmarkletの登録方法

SharePointのページから、リスト名とURLをJSONでコピーするBookmarkletを用意しています。

* コードと登録手順: [scripts/bookmarklets.md](scripts/bookmarklets.md)

コピーした内容は、画面右上の「貼り付け取込」に貼り付けて解析・保存します。

## データ保存場所

```text
data/list_nexus.sqlite3
```

* SQLite（WALモード）で保存します。Git管理対象外です。
* 認証情報、Cookie、アクセストークンは一切保存しません。
* Bookmarkletが取得するのはページタイトルとURLのみで、HTML本文は保存しません。

## JSONバックアップ

* 画面右上の「バックアップ」ボタンで `list-nexus-backup-YYYYMMDD-HHMMSS.json` をダウンロードできます。
* 「JSON復元」ボタンから、そのファイルを読み込んで再取り込みできます。
* 重複（一覧URLが同じ）の場合の動作は「スキップ / 既存を更新 / エラーとして扱う」から選べます（初期値はスキップ）。
* 「既存を更新」は、JSONの内容で既存レコードを**上書き**します（JSONに無い項目は空になります）。

書式：

```json
{
  "schemaVersion": 1,
  "exportedAt": "2026-07-27T15:30:00+09:00",
  "lists": [
    {
      "name": "障害管理",
      "listUrl": "https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx",
      "newItemUrl": "",
      "settingsUrl": "",
      "siteName": "開発部",
      "group": "開発",
      "tags": ["障害", "本番"],
      "environment": "production",
      "description": "",
      "favorite": true,
      "sortOrder": 0
    }
  ]
}
```

## テスト実行方法

```bash
python -m pytest
```

`import_parser` / `url_utils` / `repositories` の主要処理をテストしています（テスト用の一時SQLite DBを使用）。

## ソース構成

| ファイル | 責務 |
| --- | --- |
| `app.py` | Streamlit UI（画面とダイアログのみ） |
| `styles.py` | CSSとHTML片の生成（ユーザー入力は必ずエスケープ） |
| `repositories.py` | listsテーブルへのデータアクセス、絞り込み、インポート保存 |
| `models.py` | データモデル、入力検証、DB行・エクスポート形式との変換 |
| `database.py` | SQLite接続、PRAGMA設定、スキーマ初期化、トランザクション |
| `import_parser.py` | 貼り付けテキスト・JSONの解析 |
| `url_utils.py` | URL検証、新規作成URL候補の生成 |
| `constants.py` | 共通定数（環境値、パス、上限値など） |

## Git管理方針

* 実装は意味のある単位でコミットします。
* `.venv/`、SQLiteデータベース、キャッシュ、IDE設定（PyCharmの `.idea/` を含む）はコミットしません。
* `data/.gitkeep` はGit管理します。

## 既知の制約

* Microsoft Graph API連携、Entra ID認証、SharePointからのリスト自動取得は行いません（初期バージョン対象外）。
* `open_count` カラムは仕様どおり作成していますが、**初期バージョンでは加算していません**。
  リンクは新しいタブを開くだけでアプリ側へ通知されず、クリックを正確に検知できないためです。
  加算用のAPI（`ListRepository.increment_open_count`）は残してあり、画面には表示していません。
* 新規作成URLの自動生成は**候補**です。Power Appsカスタムフォームや独自ビューでは正しくない場合があるため、
  必ず生成結果を確認・編集してください（生成時はクエリ文字列とフラグメントを除去します）。
* 削除は物理削除です。ゴミ箱機能はありません。
* 並び順の「リスト名」はUnicodeコードポイント順です（日本語の読み仮名順にはなりません）。
* サイドバーの「環境」フィルターには、実際に登録データで使われている環境のみが表示されます。
* URLのみを貼り付けた場合、リスト名はURLから推測しません。プレビューで入力してください。
* スマートフォン表示は最適化していません（狭い画面でも崩れない程度の対応のみ）。
* 単一ユーザー・ローカル利用専用です。同じDBを複数プロセスから同時更新することは想定していません。

## 実装上の判断メモ

仕様に明記がなく、実装時に判断した点です。

* 日時は**ローカル時刻（タイムゾーン付きISO 8601）**で統一しました（例: `2026-07-27T15:30:00+09:00`）。
* `.streamlit/config.toml` を追加し、待ち受けアドレス `127.0.0.1` とダークテーマの既定値を設定しました。
  秘密情報を扱う `secrets.toml` は使用せず、`.gitignore` で除外しています。
* HTMLを出力する箇所（タイルの名称・タグ等）は、`styles.escape_html()` を通してから埋め込んでいます。
  CSSと構造は固定文字列で、ユーザー入力を生のHTMLとして扱う箇所はありません。
* 貼り付けテキストが `{` で始まる場合はJSONとしてのみ解析し、`[` で始まる場合はJSON配列 → Markdownリンクの順に試します。
  （Markdownリンクも `[` で始まるためです。）
* グループ未設定のリストは「未分類」として扱い、サイドバーのグループフィルターからも選択できます。
* 行末の改行コード差分を避けるため `.gitattributes` を追加しました（`.bat` はCRLF、`.py`/`.md` はLF）。
* エディタ設定として `.gitignore` にPyCharm（JetBrains）向けの除外（`.idea/`、`*.iml` など）を追加しました。

## ライセンス

MIT License です。詳細は [LICENSE](LICENSE) を参照してください。

## トラブルシューティング

**`start.bat` が「Python仮想環境がありません」と表示する**
`setup.bat` を先に実行してください。

**ポート8501が使用中**
既にLIST NEXUSまたは別のStreamlitアプリが起動しています。既存のウィンドウを閉じるか、
コマンドラインから `--server.port 8502` を指定して起動してください。

**「この一覧URLは既に登録されています」と表示される**
一覧URLはデータベース内で一意です。クエリ文字列（`?viewid=...`）の有無で別URLとして扱われる点に注意してください。
既存のリストを直したい場合は、そのタイルの「編集」から変更してください。

**貼り付け取込で「URLを見つけられませんでした」と表示される**
`http://` または `https://` で始まるURLが含まれているか確認してください。
`javascript:` や `data:` のURLは安全のため受け付けません。

**データを初期状態に戻したい**
アプリを終了してから `data/list_nexus.sqlite3`（および `-wal` / `-shm` ファイル）を削除してください。
次回起動時に空のデータベースが再作成されます。削除前に「バックアップ」でJSONを保存しておくことを推奨します。

**画面表示が崩れる / 古い状態が残る**
ブラウザで `Ctrl + F5`（キャッシュを無視した再読み込み）を実行してください。

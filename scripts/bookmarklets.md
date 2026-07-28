# LIST NEXUS Bookmarklet

SharePoint / Microsoft Lists のページを開いたまま、リスト情報をJSONとしてクリップボードへコピーするためのBookmarkletです。

コピーした内容は、LIST NEXUS の「貼り付け取込」ダイアログへそのまま貼り付けられます。

## 登録方法（Microsoft Edge）

1. `Ctrl + Shift + O` でお気に入り管理を開く
2. 右クリック → 「お気に入りを追加」
3. 名前に `LN 一覧取得` などを入力
4. URL欄に、下のコードを**1行のまま**貼り付ける
5. 保存する

対象のSharePointページを開いた状態で、そのお気に入りをクリックすると実行されます。

> クリップボードへの書き込みがブロックされた場合は、代わりにテキスト入力ダイアログが開きます。表示された内容を手動でコピーしてください。

## 8.1 一覧ページ取得Bookmarklet

現在のページタイトルとURLを取得し、以下の形式でコピーします。

```json
{
  "name": "障害管理",
  "listUrl": "https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx",
  "sourceTitle": "障害管理 - Microsoft Lists",
  "capturedAt": "2026-07-27T12:00:00.000Z"
}
```

```javascript
javascript:(async()=>{const data={name:document.title.replace(/\s*-\s*Microsoft Lists.*$/i,'').replace(/\s*-\s*SharePoint.*$/i,'').trim(),listUrl:location.href,sourceTitle:document.title,capturedAt:new Date().toISOString()};const text=JSON.stringify(data,null,2);try{await navigator.clipboard.writeText(text);alert('リスト情報をコピーしました\n\n'+data.name);}catch(e){prompt('コピーしてください',text);}})();
```

## 8.2 新規作成ページ取得Bookmarklet

新規作成フォーム（NewForm.aspx やカスタムフォーム）を開いた状態で実行します。

```json
{
  "action": "newItem",
  "name": "障害管理",
  "newItemUrl": "https://example.sharepoint.com/sites/dev/Lists/Issues/NewForm.aspx",
  "capturedAt": "2026-07-27T12:00:00.000Z"
}
```

```javascript
javascript:(async()=>{const data={action:"newItem",name:document.title.replace(/\s*-\s*Microsoft Lists.*$/i,'').replace(/\s*-\s*SharePoint.*$/i,'').trim(),newItemUrl:location.href,capturedAt:new Date().toISOString()};const text=JSON.stringify(data,null,2);try{await navigator.clipboard.writeText(text);alert('新規作成URLをコピーしました');}catch(e){prompt('コピーしてください',text);}})();
```

このJSONには一覧URLが含まれないため、貼り付け取込のプレビューで
「新規作成URLのみのデータです。対応する一覧URLを入力してください。」と表示されます。
一覧URLを入力してから保存してください。

既に登録済みのリストへ新規作成URLだけを追加したい場合は、
タイルの「編集」から `新規作成URL` に貼り付けるほうが簡単です。

## 補足

* Bookmarkletが取得するのはページタイトルとURLのみです。ページ本文やCookie、認証トークンは取得しません。
* `capturedAt` と `sourceTitle` はLIST NEXUS側では保存されません（取り込み時に無視されます）。
* 一覧URLからの新規作成URLは、登録ダイアログの「新規作成URLの候補を生成」でも作れます。
  ただし候補にすぎないため、Power Appsカスタムフォームなどでは実際のURLを確認してください。

# LIST NEXUS Bookmarklet

SharePoint / Microsoft Lists のページから、リスト情報をJSONとしてクリップボードへコピーするためのBookmarkletです。

コピーした内容は、LIST NEXUS の「貼り付け取込」ダイアログへそのまま貼り付けられます。

読みやすいソースは [scripts/bookmarklets/](bookmarklets/) にあります（**そちらが原本**）。
このファイルの1行版は、そのソースから書き起こしたものです。挙動を変えるときは両方直してください。

| Bookmarklet | 取得できるもの | 実行する場所 |
| --- | --- | --- |
| [サイト内の全リスト一括取得](#サイト内の全リスト一括取得) | サイトのリスト／ライブラリを**全件** | SharePointサイトの任意のページ |
| [ページ内リンク一括取得](#ページ内リンク一括取得) | ページ内の同一ドメインリンクを全件 | どのWebページでも可 |
| [一覧ページ取得](#一覧ページ取得specの81) | 開いているページ1件 | リストの一覧ページ |
| [新規作成ページ取得](#新規作成ページ取得specの82) | 開いているページの新規作成URL1件 | 新規作成フォーム |

大量に登録したいときは **「サイト内の全リスト一括取得」** を使ってください。1サイト分が1回で入ります。

## 登録方法（Microsoft Edge）

1. `Ctrl + Shift + O` でお気に入り管理を開く
2. 右クリック → 「お気に入りを追加」
3. 名前に `LN 全リスト取得` などを入力
4. URL欄に、下のコードを**1行のまま**貼り付ける
5. 保存する

対象のページを開いた状態で、そのお気に入りをクリックすると実行されます。

> クリップボードへの書き込みがブロックされた場合は、画面上にテキスト欄が現れます。`Ctrl + A` → `Ctrl + C` でコピーしてください。

---

## サイト内の全リスト一括取得

そのサイトのリスト／ライブラリを SharePoint の REST API (`/_api/web/lists`) からまとめて取得します。
**ブラウザの既存ログインセッションで呼ぶだけ**で、Microsoft Graph API や Entra ID の追加認証は使いません（SPEC §4.2の対象外事項には触れません）。

取得内容: リスト名 / 一覧URL / 新規作成URL（候補）/ 設定URL / サイト名 / 説明
非表示リストとシステムリストは除外し、リスト名の昇順で並べます。最大500件です。

出力形式（そのまま「貼り付け取込」へ）:

```json
[
  {
    "name": "障害管理",
    "listUrl": "https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx",
    "newItemUrl": "https://example.sharepoint.com/sites/dev/Lists/Issues/NewForm.aspx",
    "settingsUrl": "https://example.sharepoint.com/sites/dev/_layouts/15/listedit.aspx?List=%7B...%7D",
    "siteName": "開発部サイト",
    "description": ""
  }
]
```

ソース: [bookmarklets/collect-site-lists.js](bookmarklets/collect-site-lists.js)

```javascript
javascript:(async()=>{const c=window._spPageContextInfo||{};const f=()=>{const m=location.pathname.match(/^\/(sites|teams)\/[^/]+/i);return location.origin+(m?m[0]:'');};const s=String(c.webAbsoluteUrl||f()).replace(/\/+$/,'');const h={Accept:'application/json;odata=nometadata'};const cp=async(t,m)=>{try{await navigator.clipboard.writeText(t);alert(m);}catch(e){const a=document.createElement('textarea');a.value=t;a.style.cssText='position:fixed;z-index:2147483647;top:5%;left:5%;width:90%;height:70%;font-size:12px;';document.body.appendChild(a);a.focus();a.select();alert('クリップボードへ書き込めませんでした。表示されたテキストをCtrl+Cでコピーしてください。');}};try{const wr=await fetch(s+'/_api/web?$select=Title',{headers:h,credentials:'same-origin'});if(!wr.ok)throw new Error('web '+wr.status);const w=await wr.json();const q='/_api/web/lists?$select=Title,Id,Description,BaseTemplate,DefaultViewUrl,Hidden,IsSystemList&$filter=Hidden eq false&$top=500';const lr=await fetch(s+q,{headers:h,credentials:'same-origin'});if(!lr.ok)throw new Error('lists '+lr.status);const p=await lr.json();const es=(p.value||[]).filter(i=>!i.IsSystemList&&i.DefaultViewUrl).map(i=>{const u=location.origin+i.DefaultViewUrl;return{name:i.Title,listUrl:u,newItemUrl:i.BaseTemplate===101?'':u.replace(/\/[^/]+$/,'/NewForm.aspx'),settingsUrl:s+'/_layouts/15/listedit.aspx?List=%7B'+String(i.Id).replace(/[{}]/g,'')+'%7D',siteName:w.Title||'',description:i.Description||''};}).sort((a,b)=>a.name.localeCompare(b.name,'ja'));if(!es.length){alert('取得できるリストがありませんでした。');return;}await cp(JSON.stringify(es,null,2),es.length+'件のリストをコピーしました。\n\nLIST NEXUS の「貼り付け取込」に貼り付けてください。');}catch(e){alert('リスト情報を取得できませんでした。\nSharePointサイトのページで実行してください。\n\n'+e.message);}})();
```

注意点:

* **新規作成URLは候補です。** 既定ビューのURLから機械的に組み立てているため、Power Appsカスタムフォームや独自フォームのリストでは実際のURLと異なります。取込プレビューで確認してください。
* ドキュメントライブラリには新規作成フォームがないため、新規作成URLは空になります。
* 「リスト情報を取得できませんでした」と出る場合は、SharePointサイトのページで実行しているか確認してください。テナントの設定でREST APIが制限されている場合は、下の「ページ内リンク一括取得」やExcelからのタブ区切り貼り付けを使ってください。

## ページ内リンク一括取得

開いているページの**同一ドメインのリンク**を、リンク文字列を名前として全件コピーします。
SharePointのハブページやリンク集からの取り込みに使えます。

どのWebページでも動くので、**SharePointにアクセスできない環境で貼り付け取込の動作確認**にも使えます。

リンク文字列が空のもの、別ドメイン、URL重複は除外します。最大300件です。

ソース: [bookmarklets/collect-page-links.js](bookmarklets/collect-page-links.js)

```javascript
javascript:(async()=>{const L=300;const seen={};const es=[];const as=document.querySelectorAll('a[href]');for(let i=0;i<as.length;i++){const a=as[i];const u=a.href;if(!/^https?:/i.test(u))continue;if(a.hostname!==location.hostname)continue;if(seen[u])continue;const t=(a.innerText||a.textContent||'').replace(/\s+/g,' ').trim();const n=t||(a.getAttribute('title')||'').trim();if(!n)continue;seen[u]=true;es.push({name:n,listUrl:u});if(es.length>=L)break;}if(!es.length){alert('コピーできるリンクが見つかりませんでした。');return;}const tx=JSON.stringify(es,null,2);const ms=es.length+'件のリンクをコピーしました。\n\nLIST NEXUS の「貼り付け取込」に貼り付けてください。';try{await navigator.clipboard.writeText(tx);alert(ms);}catch(e){const a2=document.createElement('textarea');a2.value=tx;a2.style.cssText='position:fixed;z-index:2147483647;top:5%;left:5%;width:90%;height:70%;font-size:12px;';document.body.appendChild(a2);a2.focus();a2.select();alert('クリップボードへ書き込めませんでした。表示されたテキストをCtrl+Cでコピーしてください。');}})();
```

## 一覧ページ取得（SPECの8.1）

現在のページタイトルとURLを1件分だけコピーします。

```json
{
  "name": "障害管理",
  "listUrl": "https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx",
  "sourceTitle": "障害管理 - Microsoft Lists",
  "capturedAt": "2026-07-27T12:00:00.000Z"
}
```

ソース: [bookmarklets/capture-list.js](bookmarklets/capture-list.js)

```javascript
javascript:(async()=>{const data={name:document.title.replace(/\s*-\s*Microsoft Lists.*$/i,'').replace(/\s*-\s*SharePoint.*$/i,'').trim(),listUrl:location.href,sourceTitle:document.title,capturedAt:new Date().toISOString()};const text=JSON.stringify(data,null,2);try{await navigator.clipboard.writeText(text);alert('リスト情報をコピーしました\n\n'+data.name);}catch(e){prompt('コピーしてください',text);}})();
```

## 新規作成ページ取得（SPECの8.2）

新規作成フォーム（NewForm.aspx やカスタムフォーム）を開いた状態で実行します。

```json
{
  "action": "newItem",
  "name": "障害管理",
  "newItemUrl": "https://example.sharepoint.com/sites/dev/Lists/Issues/NewForm.aspx",
  "capturedAt": "2026-07-27T12:00:00.000Z"
}
```

ソース: [bookmarklets/capture-new-item.js](bookmarklets/capture-new-item.js)

```javascript
javascript:(async()=>{const data={action:"newItem",name:document.title.replace(/\s*-\s*Microsoft Lists.*$/i,'').replace(/\s*-\s*SharePoint.*$/i,'').trim(),newItemUrl:location.href,capturedAt:new Date().toISOString()};const text=JSON.stringify(data,null,2);try{await navigator.clipboard.writeText(text);alert('新規作成URLをコピーしました');}catch(e){prompt('コピーしてください',text);}})();
```

このJSONには一覧URLが含まれないため、貼り付け取込のプレビューで
「新規作成URLのみのデータです。対応する一覧URLを入力してください。」と表示されます。
一覧URLを入力してから保存してください。
既に登録済みのリストへ新規作成URLだけを追加したい場合は、タイルの「編集」から貼るほうが簡単です。

---

## Excelから大量に貼り付ける（Bookmarkletを使わない方法）

「名前」「一覧URL」の2列を**タブ区切り**で貼り付けても取り込めます。Excelでコピーすれば自動的にタブ区切りになります。

```text
障害管理	https://example.sharepoint.com/sites/dev/Lists/Issues/AllItems.aspx
端末管理	https://example.sharepoint.com/sites/dev/Lists/Devices/AllItems.aspx
```

1行目に見出し行（`リスト名  一覧URL` など）が入っていても、URLを含まない行として無視されます。
カンマ区切りは名前の末尾にカンマが残るため使わないでください。

3列目以降（グループやタグ）は現在は読み取れません。必要になったら見出し行に対応したTSV取込を追加します。

## 取得しない情報

Bookmarkletが取得するのは、リスト名・URL・説明などの**リンク情報のみ**です。

* リストのアイテム（中身）は取得しません
* ページのHTML本文は保存しません
* Cookie、パスワード、アクセストークンは取得も保存もしません
* `capturedAt` と `sourceTitle` はLIST NEXUS側では保存されません（取り込み時に無視されます）

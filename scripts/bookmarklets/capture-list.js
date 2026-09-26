/*
 * 一覧ページ取得Bookmarklet（LIST NEXUS / SPEC 8.1）
 *
 * 今開いているページのタイトルとURLを1件分のJSONにしてクリップボードへコピーする。
 * タイトル末尾の「- Microsoft Lists」「- SharePoint」は除去する。
 *
 * このファイルが原本。scripts/bookmarklets.md の1行版はここから書き起こしている。
 */
(async () => {
  const name = document.title
    .replace(/\s*-\s*Microsoft Lists.*$/i, '')
    .replace(/\s*-\s*SharePoint.*$/i, '')
    .trim();
  const data = {
    name: name,
    listUrl: location.href,
    sourceTitle: document.title,
    capturedAt: new Date().toISOString()
  };
  const text = JSON.stringify(data, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    alert('リスト情報をコピーしました\n\n' + data.name);
  } catch (err) {
    prompt('コピーしてください', text);
  }
})();

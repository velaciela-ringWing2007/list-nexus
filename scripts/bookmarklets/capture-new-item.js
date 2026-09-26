/*
 * 新規作成ページ取得Bookmarklet（LIST NEXUS / SPEC 8.2）
 *
 * 新規作成フォームを開いた状態で実行し、そのURLをJSONにしてコピーする。
 * 一覧URLは含まれないため、取込プレビューで一覧URLを入力する必要がある。
 * 既に登録済みのリストへ追加するだけなら、タイルの「編集」から貼るほうが早い。
 *
 * このファイルが原本。scripts/bookmarklets.md の1行版はここから書き起こしている。
 */
(async () => {
  const name = document.title
    .replace(/\s*-\s*Microsoft Lists.*$/i, '')
    .replace(/\s*-\s*SharePoint.*$/i, '')
    .trim();
  const data = {
    action: 'newItem',
    name: name,
    newItemUrl: location.href,
    capturedAt: new Date().toISOString()
  };
  const text = JSON.stringify(data, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    alert('新規作成URLをコピーしました');
  } catch (err) {
    prompt('コピーしてください', text);
  }
})();

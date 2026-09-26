/*
 * 開いているリストを1件だけ取得するBookmarklet（LIST NEXUS / SPEC 8.1）
 *
 * SharePointのリスト画面で実行すると、そのリストの情報をREST APIから取得し、
 * 「貼り付け取込」にそのまま貼れるJSONを1件分コピーする。
 * 新しく作ったリストを、その場でピンポイントに登録するための入口。
 *
 * 取得の流れ:
 *  1. ページに埋め込まれたリストID(_spPageContextInfo.pageListId)があればそれを使う
 *  2. 無ければURLからリストのフォルダを割り出し、/_api/web/getList で引く
 *     例: /sites/dev/Lists/Issues/AllItems.aspx        -> /sites/dev/Lists/Issues
 *         /sites/dev/Shared Documents/Forms/AllItems.aspx -> /sites/dev/Shared Documents
 *  3. RESTが使えないページでは、ページタイトルと現在のURLにフォールバックする
 *
 * APIを使うとリスト名が正確になり（画面タイトルの余計な装飾が付かない）、
 * 一覧URLもビュー固有のクエリを含まない正規の形になる。
 *
 * このファイルが原本。scripts/bookmarklets.md の1行版はここから書き起こしている。
 */
(async () => {
  const ctx = window._spPageContextInfo || {};
  const fallbackSite = () => {
    const matched = location.pathname.match(/^\/(sites|teams)\/[^/]+/i);
    return location.origin + (matched ? matched[0] : '');
  };
  const site = String(ctx.webAbsoluteUrl || fallbackSite()).replace(/\/+$/, '');
  const headers = { Accept: 'application/json;odata=nometadata' };

  const copy = async (data, message) => {
    const text = JSON.stringify(data, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      alert(message);
    } catch (err) {
      prompt('コピーしてください', text);
    }
  };

  // ページタイトルから装飾を取り除く（フォールバック用）
  const titleName = () =>
    document.title
      .replace(/\s*-\s*Microsoft Lists.*$/i, '')
      .replace(/\s*-\s*SharePoint.*$/i, '')
      .replace(/\s*-\s*すべてのアイテム.*$/, '')
      .trim();

  // URLからリストのフォルダ（サーバー相対）を割り出す
  const listFolder = () => {
    const path = decodeURIComponent(location.pathname);
    const cut = path.replace(/\/[^/]*\.aspx$/i, '');
    return cut.replace(/\/Forms$/i, '');
  };

  const listId = String(ctx.pageListId || ctx.listId || '').replace(/[{}]/g, '');

  try {
    const webResponse = await fetch(site + '/_api/web?$select=Title', {
      headers: headers,
      credentials: 'same-origin'
    });
    if (!webResponse.ok) throw new Error('web ' + webResponse.status);
    const web = await webResponse.json();

    const select = '?$select=Title,Id,Description,DefaultViewUrl';
    const endpoint = listId
      ? site + "/_api/web/lists(guid'" + listId + "')" + select
      : site + "/_api/web/getList('" + encodeURI(listFolder().replace(/'/g, "''")) + "')" + select;

    const listResponse = await fetch(endpoint, { headers: headers, credentials: 'same-origin' });
    if (!listResponse.ok) throw new Error('list ' + listResponse.status);
    const item = await listResponse.json();
    if (!item || !item.Title) throw new Error('list not found');

    const guid = String(item.Id).replace(/[{}]/g, '');
    await copy(
      {
        name: item.Title,
        // 空白を含むライブラリ名でも壊れないよう、空白だけをエンコードする
        listUrl: item.DefaultViewUrl
          ? location.origin + item.DefaultViewUrl.replace(/ /g, '%20')
          : location.href,
        settingsUrl: site + '/_layouts/15/listedit.aspx?List=%7B' + guid + '%7D',
        siteName: web.Title || '',
        description: item.Description || ''
      },
      'このリストをコピーしました\n\n' + item.Title
    );
  } catch (err) {
    // SharePointのAPIが使えないページでも、名前とURLだけは拾えるようにする
    await copy(
      { name: titleName(), listUrl: location.href, sourceTitle: document.title },
      'ページのタイトルとURLをコピーしました（API未使用）\n\n' + titleName()
    );
  }
})();

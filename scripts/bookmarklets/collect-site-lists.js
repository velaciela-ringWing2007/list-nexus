/*
 * サイト内の全リスト一括取得Bookmarklet（LIST NEXUS）
 *
 * SharePointサイトの任意のページで実行すると、そのサイトのリスト／ライブラリを
 * REST API (/_api/web/lists) からまとめて取得し、LIST NEXUS の
 * 「貼り付け取込」にそのまま貼れるJSON配列をクリップボードへコピーする。
 *
 * - ブラウザの既存ログインセッション（Cookie）で呼ぶだけで、
 *   Microsoft Graph APIやEntra IDの追加認証は使わない。
 * - 取得するのはリスト名・URL・説明のみ。アイテムの中身は取得しない。
 * - 設定URLはリスト設定ページ(listedit.aspx)を指す。
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

  const copy = async (text, message) => {
    try {
      await navigator.clipboard.writeText(text);
      alert(message);
    } catch (err) {
      const area = document.createElement('textarea');
      area.value = text;
      area.style.cssText =
        'position:fixed;z-index:2147483647;top:5%;left:5%;width:90%;height:70%;font-size:12px;';
      document.body.appendChild(area);
      area.focus();
      area.select();
      alert('クリップボードへ書き込めませんでした。表示されたテキストをCtrl+Cでコピーしてください。');
    }
  };

  try {
    const webResponse = await fetch(site + '/_api/web?$select=Title', {
      headers: headers,
      credentials: 'same-origin'
    });
    if (!webResponse.ok) throw new Error('web ' + webResponse.status);
    const web = await webResponse.json();

    const query =
      '/_api/web/lists?$select=Title,Id,Description,DefaultViewUrl,Hidden,IsSystemList' +
      '&$filter=Hidden eq false&$top=500';
    const listResponse = await fetch(site + query, {
      headers: headers,
      credentials: 'same-origin'
    });
    if (!listResponse.ok) throw new Error('lists ' + listResponse.status);
    const payload = await listResponse.json();

    const lists = (payload.value || []).filter((item) => !item.IsSystemList && item.DefaultViewUrl);
    const entries = lists
      .map((item) => {
        const guid = String(item.Id).replace(/[{}]/g, '');
        return {
          name: item.Title,
          listUrl: location.origin + item.DefaultViewUrl,
          settingsUrl: site + '/_layouts/15/listedit.aspx?List=%7B' + guid + '%7D',
          siteName: web.Title || '',
          description: item.Description || ''
        };
      })
      .sort((a, b) => a.name.localeCompare(b.name, 'ja'));

    if (!entries.length) {
      alert('取得できるリストがありませんでした。');
      return;
    }
    await copy(
      JSON.stringify(entries, null, 2),
      entries.length + '件のリストをコピーしました。\n\nLIST NEXUS の「貼り付け取込」に貼り付けてください。'
    );
  } catch (err) {
    alert(
      'リスト情報を取得できませんでした。\nSharePointサイトのページで実行してください。\n\n' + err.message
    );
  }
})();

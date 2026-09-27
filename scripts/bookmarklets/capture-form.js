/*
 * 開いているMicrosoft Formsを1件取得するBookmarklet（LIST NEXUS）
 *
 * Formsのデザイン画面（編集画面）で実行すると、
 * フォーム名・編集ページ・回答ページをJSONでコピーする。
 *
 * 取得の考え方:
 *  - フォームIDはURLの id パラメータに入っている
 *      https://forms.office.com/Pages/DesignPageV2.aspx?...&id=<フォームID>
 *  - 回答ページは同じIDで組み立てられる
 *      https://forms.office.com/Pages/ResponsePage.aspx?id=<フォームID>
 *  - フォーム名はページタイトルから「- Microsoft Forms」などの装飾を落として使う
 *
 * listUrl には編集ページを入れる（管理が目的のため）。
 * settingsUrl には回答ページを入れる。逆にしたい場合は取込プレビューで入れ替える。
 *
 * Forms の API はアクセストークンを必要とし、Cookieだけでは呼べないため、
 * SharePointのBookmarkletのようなREST取得は行わない。
 *
 * このファイルが原本。scripts/bookmarklets.md の1行版はここから書き起こしている。
 */
(async () => {
  const params = new URLSearchParams(location.search);
  const formId = params.get('id') || '';

  const name = document.title
    .replace(/\s*-\s*Microsoft Forms.*$/i, '')
    .replace(/\s*-\s*Forms.*$/i, '')
    .replace(/^Microsoft Forms\s*[-|]?\s*/i, '')
    .trim();

  if (!formId) {
    alert(
      'フォームIDが見つかりませんでした。\n' +
        'Formsのデザイン画面（URLに id= を含むページ）で実行してください。'
    );
    return;
  }

  const data = {
    name: name || '名称未設定のフォーム',
    space: 'Forms',
    listUrl: location.origin + '/Pages/DesignPageV2.aspx?id=' + encodeURIComponent(formId),
    settingsUrl: location.origin + '/Pages/ResponsePage.aspx?id=' + encodeURIComponent(formId),
    description: ''
  };

  const text = JSON.stringify(data, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    alert('フォームをコピーしました\n\n' + data.name);
  } catch (err) {
    prompt('コピーしてください', text);
  }
})();

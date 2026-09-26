/*
 * ページ内リンク一括取得Bookmarklet（LIST NEXUS）
 *
 * 今開いているページの同一ドメインのリンクを、リンク文字列を名前として
 * まとめてJSON配列にしてクリップボードへコピーする。
 *
 * 用途:
 * - SharePointのハブページやリンク集ページからまとめて登録する
 * - SharePointにアクセスできない環境で、貼り付け取込の動作確認をする
 *   （どのWebページでも動くため、個人PCでも試せる）
 *
 * 別ドメインへのリンクとリンク文字列が空のものは除外し、URLの重複も除く。
 * 件数が多いページでも扱えるよう、最大 LIMIT 件までとする。
 *
 * このファイルが原本。scripts/bookmarklets.md の1行版はここから書き起こしている。
 */
(async () => {
  const LIMIT = 300;
  const seen = {};
  const entries = [];

  const anchors = document.querySelectorAll('a[href]');
  for (let i = 0; i < anchors.length; i++) {
    const anchor = anchors[i];
    const href = anchor.href;
    if (!/^https?:/i.test(href)) continue;
    if (anchor.hostname !== location.hostname) continue;
    if (seen[href]) continue;
    const text = (anchor.innerText || anchor.textContent || '').replace(/\s+/g, ' ').trim();
    const name = text || (anchor.getAttribute('title') || '').trim();
    if (!name) continue;
    seen[href] = true;
    entries.push({ name: name, listUrl: href });
    if (entries.length >= LIMIT) break;
  }

  if (!entries.length) {
    alert('コピーできるリンクが見つかりませんでした。');
    return;
  }

  const text = JSON.stringify(entries, null, 2);
  const message =
    entries.length + '件のリンクをコピーしました。\n\nLIST NEXUS の「貼り付け取込」に貼り付けてください。';
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
})();

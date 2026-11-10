// Mise en forme Discord -> HTML sûr.
// Principe : tout le texte est échappé AVANT d'ajouter nos propres balises ; seuls les liens http(s) sont acceptés.
(function (root) {
  const esc = s => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function formatDiscord(raw, mentions) {
    mentions = mentions || { users: {}, roles: {}, channels: {} };
    const stash = [];
    const keep = html => '\u0000' + (stash.push(html) - 1) + '\u0000';
    let s = String(raw || '').replace(/\u0000/g, '');

    // 1. Code : rien n'est interprété à l'intérieur
    s = s.replace(/```(?:[\w+-]*\n)?([\s\S]*?)```\n?/g, (_, code) => keep('<pre><code>' + esc(code.replace(/\n$/, '')) + '</code></pre>'));
    s = s.replace(/`([^`\n]+)`/g, (_, code) => keep('<code>' + esc(code) + '</code>'));

    // 2. Liens (avant l'échappement pour lire l'URL telle quelle)
    s = s.replace(/\[([^\]\n]+)\]\(<?(https?:\/\/[^\s)>]+)>?\)|<?(https?:\/\/[^\s<>]+[^\s<>.,;:!?)\]'"])>?/g, (_, label, url1, url2) => {
      const url = url1 || url2;
      return keep('<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + esc(label || url) + '</a>');
    });

    // 3. Éléments Discord <...>
    s = s.replace(/<(a?):(\w+):(\d+)>/g, (_, anim, name, id) =>
      keep('<img class="emoji" src="https://cdn.discordapp.com/emojis/' + id + (anim ? '.gif' : '.webp') + '?size=48" alt=":' + esc(name) + ':" title=":' + esc(name) + ':">'));
    const tag = (cls, text) => keep('<span class="' + cls + '">' + esc(text) + '</span>');
    s = s.replace(/<@!?(\d+)>/g, (_, id) => tag('mention', '@' + (mentions.users[id] || 'inconnu')));
    s = s.replace(/<@&(\d+)>/g, (_, id) => tag('mention', '@' + (mentions.roles[id] || 'rôle')));
    s = s.replace(/<#(\d+)>/g, (_, id) => tag('mention', '#' + (mentions.channels[id] || 'salon')));
    s = s.replace(/@(everyone|here)\b/g, (_, w) => tag('mention', '@' + w));
    s = s.replace(/<t:(-?\d+)(?::([tTdDfFR]))?>/g, (_, t, f) => {
      const d = new Date(Number(t) * 1000);
      const txt = f === 'R' ? relative(d) : f === 'd' || f === 'D' ? d.toLocaleDateString('fr-FR') : f === 't' || f === 'T' ? d.toLocaleTimeString('fr-FR') : d.toLocaleString('fr-FR');
      return tag('time', txt);
    });

    // 4. Échappement de tout le reste
    s = esc(s);

    // 5. Styles (ordre : *** avant ** avant *)
    s = s.replace(/\*\*\*(.+?)\*\*\*/g, '<b><i>$1</i></b>')
         .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
         .replace(/__(.+?)__/g, '<u>$1</u>')
         .replace(/\*(?!\s)(.+?)\*/g, '<i>$1</i>')
         .replace(/(^|[^\w])_(?!\s)(.+?)_(?!\w)/g, '$1<i>$2</i>')
         .replace(/~~(.+?)~~/g, '<s>$1</s>')
         .replace(/\|\|(.+?)\|\|/g, '<span class="spoiler" onclick="this.classList.add(\'shown\')">$1</span>');

    // 6. Lignes : titres, citations, sous-texte
    s = s.split('\n').map(line => {
      let m;
      if ((m = line.match(/^(#{1,3}) (.+)/))) return '<span class="h' + m[1].length + '">' + m[2] + '</span>';
      if ((m = line.match(/^-# (.+)/))) return '<span class="sub">' + m[1] + '</span>';
      if ((m = line.match(/^&gt; ?(.*)/))) return '<span class="quote">' + m[1] + '</span>';
      return line;
    }).join('\n');

    // 7. Remise en place des morceaux protégés
    return s.replace(/\u0000(\d+)\u0000/g, (_, i) => stash[i]);
  }

  function relative(d) {
    const sec = Math.round((d - Date.now()) / 1000);
    const units = [['year', 31536000], ['month', 2592000], ['day', 86400], ['hour', 3600], ['minute', 60], ['second', 1]];
    const [u, n] = units.find(([, n]) => Math.abs(sec) >= n) || ['second', 1];
    return new Intl.RelativeTimeFormat('fr', { numeric: 'auto' }).format(Math.round(sec / n), u);
  }

  root.formatDiscord = formatDiscord;
  if (typeof module !== 'undefined') module.exports = formatDiscord;
})(typeof window !== 'undefined' ? window : globalThis);

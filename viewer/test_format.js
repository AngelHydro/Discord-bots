// Lancer : node test_format.js
const assert = require('assert');
const f = require('./format.js');
const M = { users: { '1': 'Alice' }, roles: { '2': 'Modo' }, channels: { '3': 'général' } };
const eq = (input, out) => assert.strictEqual(f(input, M), out, input);

// Sécurité : aucune balise de l'utilisateur ne passe
eq('<script>alert(1)</script>', '&lt;script&gt;alert(1)&lt;/script&gt;');
eq('<img src=x onerror=alert(1)>', '&lt;img src=x onerror=alert(1)&gt;');
eq('[clic](javascript:alert(1))', '[clic](javascript:alert(1))');
eq('[a"b](https://x.fr/"onmouseover=)', '<a href="https://x.fr/&quot;onmouseover=" target="_blank" rel="noopener noreferrer">a&quot;b</a>');
eq('`<b>`', '<code>&lt;b&gt;</code>');
eq('**<i>x</i>**', '<b>&lt;i&gt;x&lt;/i&gt;</b>');
eq('\u0000' + '0\u0000', '0');  // faux marqueur interne neutralisé

// Mise en forme
eq('**gras** *ital* __sous__ ~~barré~~', '<b>gras</b> <i>ital</i> <u>sous</u> <s>barré</s>');
eq('***les deux***', '<b><i>les deux</i></b>');
eq('_ital_ mais nom_de_fichier', '<i>ital</i> mais nom_de_fichier');
eq('2 * 3 * 4', '2 * 3 * 4');
eq('||secret||', '<span class="spoiler" onclick="this.classList.add(\'shown\')">secret</span>');
eq('```js\nlet a = **1**;\n```', '<pre><code>let a = **1**;</code></pre>');
eq('```\nx\n```\napres', '<pre><code>x</code></pre>apres');  // pas de ligne vide en trop
eq('# Titre\n> cité\n-# petit', '<span class="h1">Titre</span>\n<span class="quote">cité</span>\n<span class="sub">petit</span>');

// Liens
eq('va sur https://ex.fr/a_b_c.', 'va sur <a href="https://ex.fr/a_b_c" target="_blank" rel="noopener noreferrer">https://ex.fr/a_b_c</a>.');
eq('[site](https://ex.fr?a=1&b=2)', '<a href="https://ex.fr?a=1&amp;b=2" target="_blank" rel="noopener noreferrer">site</a>');

// Discord
eq('<@1> <@!1> <@&2> <#3> <@9>', '<span class="mention">@Alice</span> <span class="mention">@Alice</span> <span class="mention">@Modo</span> <span class="mention">#général</span> <span class="mention">@inconnu</span>');
eq('@everyone', '<span class="mention">@everyone</span>');
eq('<:pog:123>', '<img class="emoji" src="https://cdn.discordapp.com/emojis/123.webp?size=48" alt=":pog:" title=":pog:">');
eq('<a:dance:456>', '<img class="emoji" src="https://cdn.discordapp.com/emojis/456.gif?size=48" alt=":dance:" title=":dance:">');
assert.match(f('<t:0:d>', M), /^<span class="time">\d/);
assert.strictEqual(f(null), '');
console.log('ok');

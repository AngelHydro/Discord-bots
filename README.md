# Discord Viewer

Bot Discord qui affiche les messages des salons dans une page web façon chat (historique + direct).

Fonctions : historique complet, messages en direct, réponses, réactions, messages modifiés / supprimés,
recherche par mot ou auteur (sur les 2000 derniers messages du salon), fils et forums, mise en forme Discord
(gras, liens, code, mentions, emojis…), compteur de non-lus, notifications sur le téléphone,
membres du serveur avec leur statut et activité, salons vocaux avec les personnes connectées.

## 1. Créer le bot
1. https://discord.com/developers/applications → *New Application* → onglet **Bot** → *Reset Token* (copie-le, garde-le secret).
   ⚠️ Ce n'est **pas** la « Public Key » de l'onglet General Information : celle-là ne sert pas ici.
2. Même onglet, section *Privileged Gateway Intents* : active **Presence Intent**, **Server Members Intent**
   et **Message Content Intent** (statuts des membres, liste des membres, contenu des messages).
3. Onglet **OAuth2 → URL Generator** : scope `bot`, permissions `View Channels` + `Read Message History`.
4. Envoie l'URL générée à un admin du serveur pour qu'il invite le bot.

## 2. Lancer
```bash
pip install -r requirements.txt
```
Puis copie `.env.example` en `.env` et remplis-le (token + mot de passe). Ce fichier n'est jamais envoyé sur GitHub.

**Windows** : double-clique sur `lancer.bat`.
Pour qu'il se lance tout seul à chaque démarrage du PC (sans fenêtre) : double-clique une fois sur
`demarrage-auto.bat`. Re-double-clique dessus pour désactiver. Les erreurs éventuelles vont dans `viewer.log`.
**Linux / Mac** : `python viewer/bot.py`

Ouvre http://localhost:8080 (identifiant au choix, mot de passe = `VIEWER_PASSWORD`).

## 3. Depuis un téléphone
- **Même Wi-Fi que le PC** : ouvre l'adresse `http://192.168.x.x:8080` affichée au démarrage.
  Au premier lancement, Windows demande d'autoriser Python dans le pare-feu : coche **Réseaux privés**.
- **Hors de chez toi** : installe [Tailscale](https://tailscale.com) (gratuit) sur le PC et le téléphone,
  connecte-les au même compte, puis ouvre `http://<IP Tailscale du PC>:8080` (IP en 100.x.x.x).
  Rien n'est ouvert sur Internet, la connexion est chiffrée.

**Comme une appli** : ouvre l'adresse sur le téléphone, puis
- iPhone (Safari) : bouton Partager → *Sur l'écran d'accueil* ;
- Android (Chrome) : menu ⋮ → *Ajouter à l'écran d'accueil*.

Le PC doit rester allumé avec le bot lancé.

## 4. Notifications sur le téléphone (facultatif)
1. Installe l'appli gratuite **ntfy** (Android / iPhone).
2. Dans `.env`, mets `NTFY_TOPIC=` suivi d'un nom long et aléatoire (invente-le, ne copie pas un exemple trouvé en ligne).
   Ce nom fait office de mot de passe : quiconque le connaît peut lire les notifications.
3. Dans l'appli ntfy : **+** → s'abonner à ce même nom.
4. Relance le bot.

Filtres facultatifs dans `.env` :
- `NOTIFY_CHANNELS=annonces,général` : seulement ces salons (et leurs fils) ;
- `NOTIFY_KEYWORDS=soirée,urgent` : seulement les messages contenant un de ces mots.

Le texte des messages transite par le serveur public ntfy.sh. Pour l'éviter, tu peux héberger ntfy toi-même
et indiquer son adresse avec `NTFY_SERVER=`.

Tests : `cd viewer && python test_bot.py && node test_format.js`

> Si tu l'exposes sur Internet, mets-le derrière HTTPS (ex. Caddy), sinon le mot de passe circule en clair.

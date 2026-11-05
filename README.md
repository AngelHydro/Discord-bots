# Discord Viewer

Bot Discord qui affiche les messages des salons dans une page web façon chat (historique + direct).

Fonctions : historique complet, messages en direct, réponses, réactions, messages modifiés / supprimés,
recherche par mot ou auteur (sur les 2000 derniers messages du salon).

## 1. Créer le bot
1. https://discord.com/developers/applications → *New Application* → onglet **Bot** → *Reset Token* (copie-le, garde-le secret).
   ⚠️ Ce n'est **pas** la « Public Key » de l'onglet General Information : celle-là ne sert pas ici.
2. Même onglet : active **Message Content Intent**.
3. Onglet **OAuth2 → URL Generator** : scope `bot`, permissions `View Channels` + `Read Message History`.
4. Envoie l'URL générée à un admin du serveur pour qu'il invite le bot.

## 2. Lancer
```bash
pip install -r requirements.txt
DISCORD_TOKEN=xxx VIEWER_PASSWORD=motdepasse python viewer/bot.py
```
Ouvre http://localhost:8080 (identifiant au choix, mot de passe = `VIEWER_PASSWORD`).

Test : `cd viewer && python test_bot.py`

> Si tu l'exposes sur Internet, mets-le derrière HTTPS (ex. Caddy), sinon le mot de passe circule en clair.

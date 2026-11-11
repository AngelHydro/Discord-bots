"""Bot Discord + interface web pour lire les salons sans être sur le serveur."""
import asyncio
import base64
import errno
import hmac
import json
import os
import socket
from pathlib import Path

import aiohttp
import discord
from aiohttp import web



def load_env(path: Path):
    """Charge un fichier .env (CLE=valeur). Les variables déjà définies gardent la priorité."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


load_env(Path(__file__).resolve().parent.parent / ".env")

TOKEN = os.environ.get("DISCORD_TOKEN", "")
PASSWORD = os.environ.get("VIEWER_PASSWORD", "")
PORT = int(os.environ.get("PORT", "8080"))
HTML = Path(__file__).with_name("index.html")
FORMAT_JS = Path(__file__).with_name("format.js")
ICON = Path(__file__).with_name("icon.png")
# Le navigateur doit revérifier la page à chaque ouverture, sinon il garde une vieille version après une mise à jour.
NO_CACHE = {"Cache-Control": "no-cache"}
MANIFEST = {
    "name": "Discord Viewer",
    "short_name": "Discord",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#313338",
    "theme_color": "#2b2d31",
    "icons": [{"src": "/icon.png", "sizes": "512x512", "type": "image/png"}],
}
PUBLIC = {"/manifest.json", "/icon.png"}  # le téléphone les charge sans mot de passe ; aucune donnée Discord
SEARCH_SCAN = 2000  # ponytail: les bots n'ont pas d'API de recherche Discord, on parcourt les N derniers messages



def csv_env(name: str) -> list[str]:
    return [x.strip().lstrip("#").lower() for x in os.environ.get(name, "").split(",") if x.strip()]


# Notifications téléphone via ntfy (appli gratuite). Vide = désactivé.
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NOTIFY_CHANNELS = set(csv_env("NOTIFY_CHANNELS"))  # noms ou IDs ; vide = tous
NOTIFY_KEYWORDS = csv_env("NOTIFY_KEYWORDS")  # vide = tous les messages

READABLE = (discord.TextChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel)  # salons vocaux : leur chat texte
OFFLINE_SHOWN = 200  # ponytail: liste hors ligne tronquée, les gros serveurs en ont des milliers

intents = discord.Intents.default()
intents.message_content = True  # à activer aussi dans le Developer Portal
intents.members = True  # "Server Members Intent" dans le Developer Portal
intents.presences = True  # "Presence Intent" dans le Developer Portal
# Statut "invisible" : le bot apparaît hors ligne dans la liste des membres (il y figure toujours).
client = discord.Client(intents=intents, status=discord.Status.invisible)
listeners: set[asyncio.Queue] = set()
http: aiohttp.ClientSession | None = None
pending: set[asyncio.Task] = set()


def lan_ip() -> str:
    """IP du PC sur le réseau local (aucun paquet n'est envoyé)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.168.0.1", 1))
            return s.getsockname()[0]
        except OSError:
            return "IP-du-PC"


def to_json(m: discord.Message) -> dict:
    ref = m.reference.resolved if m.reference else None
    if isinstance(ref, discord.Message):
        reply = {"author": ref.author.display_name, "content": ref.clean_content[:120]}
    elif isinstance(ref, discord.DeletedReferencedMessage):
        reply = {"author": "", "content": "Message original supprimé"}
    else:
        reply = None
    return {
        "id": str(m.id),
        "channel": str(m.channel.id),
        "author": m.author.display_name,
        "avatar": m.author.display_avatar.url,
        "bot": m.author.bot,
        "content": m.content,  # brut, mis en forme par format.js
        "text": m.clean_content,  # texte simple (recherche)
        "mentions": {
            "users": {str(u.id): u.display_name for u in m.mentions},
            "roles": {str(r.id): r.name for r in m.role_mentions},
            "channels": {str(c.id): c.name for c in m.channel_mentions},
        },
        "time": m.created_at.isoformat(),
        "attachments": [a.url for a in m.attachments],
        "edited": m.edited_at is not None,
        "reply": reply,
        "reactions": [
            {
                "emoji": r.emoji if isinstance(r.emoji, str) else r.emoji.name,
                "url": str(r.emoji.url) if getattr(r.emoji, "id", None) else None,
                "count": r.count,
            }
            for r in m.reactions
        ],
    }


def matches(msg: dict, q: str) -> bool:
    q = q.lower()
    return q in msg["text"].lower() or q in msg["author"].lower()


ACTIVITY_VERBS = {
    discord.ActivityType.playing: "Joue à {}",
    discord.ActivityType.streaming: "En stream : {}",
    discord.ActivityType.listening: "Écoute {}",
    discord.ActivityType.watching: "Regarde {}",
    discord.ActivityType.competing: "En compétition : {}",
}


def activity_text(activities) -> str:
    """Activité affichée sous le pseudo ; une vraie activité passe avant le statut personnalisé."""
    custom = ""
    for a in activities:
        if a.type == discord.ActivityType.custom:
            emoji = a.emoji if a.emoji and not getattr(a.emoji, "id", None) else ""  # emoji perso : pas d'image ici
            custom = f"{emoji} {a.state or a.name or ''}".strip()
        elif a.type in ACTIVITY_VERBS:
            title, artist = getattr(a, "title", None), getattr(a, "artist", None)  # Spotify
            return ACTIVITY_VERBS[a.type].format(f"{title} — {artist}" if title and artist else a.name)
    return custom


def group_members(rows: list[dict]) -> list[dict]:
    """Groupes comme Discord : rôles affichés à part (du plus haut au plus bas), En ligne, Hors ligne."""
    groups: dict[tuple, list] = {}
    for r in rows:
        hoist = r.pop("hoist")
        if r["status"] == "offline":
            key = (2, 0, "Hors ligne")
        elif hoist:
            key = (0, -hoist[0], hoist[1])
        else:
            key = (1, 0, "En ligne")
        groups.setdefault(key, []).append(r)
    out = []
    for key in sorted(groups):
        members = sorted(groups[key], key=lambda r: r["name"].casefold())
        shown = members[:OFFLINE_SHOWN] if key[0] == 2 else members
        out.append({"name": key[2], "count": len(members), "members": shown})
    return out


def should_notify(names: list[str], ids: list[str], text: str, channels: set[str], keywords: list[str]) -> bool:
    """Filtre des notifications : salon (nom ou ID, salon parent compris) puis mots-clés."""
    if channels and not channels & ({n.lower() for n in names} | set(ids)):
        return False
    text = text.lower()
    return not keywords or any(k in text for k in keywords)


def password_ok(header: str, password: str) -> bool:
    """Vérifie un en-tête HTTP Basic (identifiant libre, seul le mot de passe compte)."""
    if not password or not header.startswith("Basic "):
        return False
    try:
        _, _, given = base64.b64decode(header[6:]).decode().partition(":")
    except ValueError:
        return False
    return hmac.compare_digest(given.encode(), password.encode())


@web.middleware
async def auth(request, handler):
    if request.path not in PUBLIC and not password_ok(request.headers.get("Authorization", ""), PASSWORD):
        return web.Response(status=401, headers={"WWW-Authenticate": 'Basic realm="viewer"'})
    return await handler(request)


async def index(_):
    return web.FileResponse(HTML, headers=NO_CACHE)


async def manifest(_):
    return web.json_response(MANIFEST, content_type="application/manifest+json")


async def icon(_):
    return web.FileResponse(ICON)


async def format_js(_):
    return web.FileResponse(FORMAT_JS, headers=NO_CACHE)


def thread_json(t: discord.Thread) -> dict:
    return {"id": str(t.id), "name": t.name, "last": str(t.last_message_id or t.id)}


def voice_json(m: discord.Member) -> dict:
    v = m.voice
    return {
        "name": m.display_name,
        "avatar": m.display_avatar.url,
        "mute": bool(v and (v.self_mute or v.mute)),
        "deaf": bool(v and (v.self_deaf or v.deaf)),
        "stream": bool(v and v.self_stream),
        "video": bool(v and v.self_video),
    }


def channel_order(c) -> tuple:
    # Comme Discord : par catégorie, puis texte avant vocal, puis position.
    return (c.category.position if c.category else -1, isinstance(c, discord.VoiceChannel | discord.StageChannel), c.position)


async def channels(_):
    out = []
    for g in client.guilds:
        parents = sorted(g.text_channels + g.forums + g.voice_channels + g.stage_channels, key=channel_order)
        for c in parents:
            perms = c.permissions_for(g.me)
            voice = isinstance(c, discord.VoiceChannel | discord.StageChannel)
            if not perms.view_channel or not (voice or perms.read_message_history):
                continue
            forum = isinstance(c, discord.ForumChannel)
            out.append({
                "id": str(c.id),
                "guild": g.name,
                "guild_id": str(g.id),
                "name": c.name,
                "forum": forum,
                "voice": voice,
                "readable": perms.read_message_history,
                "connected": [voice_json(m) for m in c.members] if voice else [],
                "last": None if forum else str(c.last_message_id or 0),
                # Fils actifs. ponytail: les fils archivés des salons texte ne sont pas listés, seulement ceux des forums
                "threads": [] if voice else [thread_json(t) for t in c.threads if t.permissions_for(g.me).read_message_history],
            })
    return web.json_response(out)


def member_json(m: discord.Member) -> dict:
    hoisted = max((r for r in m.roles if r.hoist), key=lambda r: r.position, default=None)
    return {
        "name": m.display_name,
        "avatar": m.display_avatar.url,
        "status": str(m.status),  # online / idle / dnd / offline (invisible = offline)
        "activity": activity_text(m.activities),
        "color": str(m.color) if m.color.value else None,
        "bot": m.bot,
        "hoist": (hoisted.position, hoisted.name) if hoisted else None,
    }


async def members(request):
    try:
        guild = client.get_guild(int(request.match_info["id"]))
    except ValueError:
        raise web.HTTPBadRequest()
    if guild is None:
        raise web.HTTPNotFound()
    return web.json_response(group_members([member_json(m) for m in guild.members]))


async def archived(request):
    try:
        forum = client.get_channel(int(request.match_info["id"]))
    except ValueError:
        raise web.HTTPBadRequest()
    if not isinstance(forum, discord.ForumChannel):
        raise web.HTTPNotFound()
    try:
        threads = [thread_json(t) async for t in forum.archived_threads(limit=50)]
    except discord.Forbidden:
        raise web.HTTPForbidden()
    return web.json_response(threads)


async def text_channel(request) -> discord.TextChannel | discord.Thread:
    try:
        cid = int(request.match_info["id"])
    except ValueError:
        raise web.HTTPBadRequest()
    channel = client.get_channel(cid)
    if channel is None:  # fil archivé : pas en cache
        try:
            channel = await client.fetch_channel(cid)
        except discord.HTTPException:
            raise web.HTTPNotFound()
    if not isinstance(channel, READABLE):
        raise web.HTTPNotFound()
    return channel


async def messages(request):
    channel = await text_channel(request)
    try:
        before = request.query.get("before")
        before = discord.Object(int(before)) if before else None
    except ValueError:
        raise web.HTTPBadRequest()
    # Historique complet possible, y compris avant l'arrivée du bot (paquets de 50).
    msgs = [to_json(m) async for m in channel.history(limit=50, before=before)]
    return web.json_response(msgs[::-1])


async def search(request):
    channel = await text_channel(request)
    q = request.query.get("q", "").strip()
    if not q:
        raise web.HTTPBadRequest()
    found = []
    async for m in channel.history(limit=SEARCH_SCAN):
        d = to_json(m)
        if matches(d, q):
            found.append(d)
            if len(found) >= 100:
                break
    return web.json_response(found[::-1])


async def stream(request):
    resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
    await resp.prepare(request)
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    listeners.add(q)
    try:
        while True:
            try:
                data = await asyncio.wait_for(q.get(), timeout=25)
                await resp.write(f"data: {json.dumps(data)}\n\n".encode())
            except asyncio.TimeoutError:
                await resp.write(b": ping\n\n")  # garde la connexion ouverte
    except ConnectionResetError:
        pass
    finally:
        listeners.discard(q)
    return resp


def broadcast(data: dict):
    for q in list(listeners):
        if not q.full():
            q.put_nowait(data)


async def refresh(channel_id: int, message_id: int):
    """Renvoie la version à jour d'un message (édition, réactions)."""
    if not listeners:
        return
    channel = client.get_channel(channel_id)
    if not isinstance(channel, READABLE):
        return
    try:
        # ponytail: 1 appel API par événement, à regrouper si un salon spamme les réactions
        m = await channel.fetch_message(message_id)
    except discord.HTTPException:
        return
    broadcast({"type": "update", **to_json(m)})


async def notify(m: discord.Message):
    ch = m.channel
    parent = getattr(ch, "parent", None)
    names = [ch.name] + ([parent.name] if parent else [])
    ids = [str(ch.id)] + ([str(parent.id)] if parent else [])
    text = m.clean_content or ("(pièce jointe)" if m.attachments else "")
    if not text or not should_notify(names, ids, text, NOTIFY_CHANNELS, NOTIFY_KEYWORDS):
        return
    where = f"#{parent.name} › {ch.name}" if parent else f"#{ch.name}"
    try:
        # JSON = accents OK ; le nom du topic sert de mot de passe, il doit être long et aléatoire
        await http.post(NTFY_SERVER, json={
            "topic": NTFY_TOPIC,
            "title": f"{m.author.display_name} · {where}",
            "message": text[:500],
            "tags": ["speech_balloon"],
        }, timeout=aiohttp.ClientTimeout(total=10))
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        print(f"Notification ntfy échouée : {e!r}")


@client.event
async def on_ready():
    # Redemandé ici en plus de la connexion : Discord ne l'applique pas toujours dès l'identification.
    await client.change_presence(status=discord.Status.invisible)
    print(f"Connecté à Discord en tant que {client.user} (statut : invisible)")


@client.event
async def on_message(m: discord.Message):
    broadcast({"type": "new", **to_json(m)})
    if NTFY_TOPIC and http and m.author != client.user:
        task = asyncio.create_task(notify(m))
        pending.add(task)
        task.add_done_callback(pending.discard)


@client.event
async def on_thread_create(_t: discord.Thread):
    broadcast({"type": "channels"})  # la page recharge la liste des salons


@client.event
async def on_voice_state_update(_m, _before, _after):
    broadcast({"type": "channels"})  # qui est dans quel salon vocal


dirty_guilds: set[int] = set()


def members_changed(guild: discord.Guild):
    # Les statuts changent sans arrêt sur un gros serveur : un seul envoi toutes les 2 s par serveur.
    if guild.id in dirty_guilds:
        return
    dirty_guilds.add(guild.id)

    def flush():
        dirty_guilds.discard(guild.id)
        broadcast({"type": "members", "guild": str(guild.id)})

    asyncio.get_running_loop().call_later(2, flush)


@client.event
async def on_presence_update(_before, after: discord.Member):
    members_changed(after.guild)


@client.event
async def on_member_update(_before, after: discord.Member):
    members_changed(after.guild)


@client.event
async def on_member_join(m: discord.Member):
    members_changed(m.guild)


@client.event
async def on_member_remove(m: discord.Member):
    members_changed(m.guild)


@client.event
async def on_raw_message_edit(p: discord.RawMessageUpdateEvent):
    await refresh(p.channel_id, p.message_id)


@client.event
async def on_raw_reaction_add(p: discord.RawReactionActionEvent):
    await refresh(p.channel_id, p.message_id)


@client.event
async def on_raw_reaction_remove(p: discord.RawReactionActionEvent):
    await refresh(p.channel_id, p.message_id)


@client.event
async def on_raw_reaction_clear(p: discord.RawReactionClearEvent):
    await refresh(p.channel_id, p.message_id)


@client.event
async def on_raw_reaction_clear_emoji(p: discord.RawReactionClearEmojiEvent):
    await refresh(p.channel_id, p.message_id)


@client.event
async def on_raw_message_delete(p: discord.RawMessageDeleteEvent):
    broadcast({"type": "delete", "id": str(p.message_id), "channel": str(p.channel_id)})


@client.event
async def on_raw_bulk_message_delete(p: discord.RawBulkMessageDeleteEvent):
    for mid in p.message_ids:
        broadcast({"type": "delete", "id": str(mid), "channel": str(p.channel_id)})


async def main():
    if not TOKEN or not PASSWORD:
        raise SystemExit("Définis DISCORD_TOKEN et VIEWER_PASSWORD (dans le fichier .env).")
    app = web.Application(middlewares=[auth])
    app.add_routes([
        web.get("/", index),
        web.get("/manifest.json", manifest),
        web.get("/icon.png", icon),
        web.get("/format.js", format_js),
        web.get("/api/channels/{id}/archived", archived),
        web.get("/api/guilds/{id}/members", members),
        web.get("/api/channels", channels),
        web.get("/api/channels/{id}/messages", messages),
        web.get("/api/channels/{id}/search", search),
        web.get("/api/stream", stream),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "0.0.0.0", PORT).start()
    except OSError as e:
        if e.errno in (errno.EADDRINUSE, 10048):  # 10048 = port occupé sous Windows
            raise SystemExit(
                f"Le port {PORT} est déjà utilisé : le bot tourne sûrement déjà "
                f"(autre fenêtre ou démarrage automatique).\n"
                f"Ouvre directement http://localhost:{PORT}, ou ferme l'autre bot. "
                f"Sinon, mets PORT=8081 dans le fichier .env."
            )
        raise
    print(f"Interface sur http://localhost:{PORT}")
    print(f"Depuis un téléphone sur le même Wi-Fi : http://{lan_ip()}:{PORT}")
    if NTFY_TOPIC:
        print(f"Notifications ntfy actives (topic : {NTFY_TOPIC})")
    global http
    try:
        async with aiohttp.ClientSession() as http, client:
            await client.start(TOKEN)
    except discord.PrivilegedIntentsRequired:
        raise SystemExit(
            "Discord refuse la connexion : active les options du bot dans le Developer Portal\n"
            "(https://discord.com/developers/applications > ton appli > Bot > Privileged Gateway Intents) :\n"
            "  - Presence Intent\n  - Server Members Intent\n  - Message Content Intent\n"
            "Puis relance le bot."
        )


if __name__ == "__main__":
    asyncio.run(main())

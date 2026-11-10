"""Bot Discord + interface web pour lire les salons sans être sur le serveur."""
import asyncio
import base64
import errno
import hmac
import json
import os
import socket
from pathlib import Path

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
ICON = Path(__file__).with_name("icon.png")
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

intents = discord.Intents.default()
intents.message_content = True  # à activer aussi dans le Developer Portal
client = discord.Client(intents=intents)
listeners: set[asyncio.Queue] = set()


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
        "content": m.clean_content,
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
    return q in msg["content"].lower() or q in msg["author"].lower()


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
    return web.FileResponse(HTML)


async def manifest(_):
    return web.json_response(MANIFEST, content_type="application/manifest+json")


async def icon(_):
    return web.FileResponse(ICON)


async def channels(_):
    out = []
    for g in client.guilds:
        for c in g.text_channels:
            perms = c.permissions_for(g.me)
            if perms.view_channel and perms.read_message_history:
                out.append({"id": str(c.id), "name": f"{g.name} / #{c.name}"})
    return web.json_response(out)


def text_channel(request) -> discord.TextChannel:
    try:
        channel = client.get_channel(int(request.match_info["id"]))
    except ValueError:
        raise web.HTTPBadRequest()
    if not isinstance(channel, discord.TextChannel):
        raise web.HTTPNotFound()
    return channel


async def messages(request):
    channel = text_channel(request)
    try:
        before = request.query.get("before")
        before = discord.Object(int(before)) if before else None
    except ValueError:
        raise web.HTTPBadRequest()
    # Historique complet possible, y compris avant l'arrivée du bot (paquets de 50).
    msgs = [to_json(m) async for m in channel.history(limit=50, before=before)]
    return web.json_response(msgs[::-1])


async def search(request):
    channel = text_channel(request)
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
    if not isinstance(channel, discord.TextChannel):
        return
    try:
        # ponytail: 1 appel API par événement, à regrouper si un salon spamme les réactions
        m = await channel.fetch_message(message_id)
    except discord.HTTPException:
        return
    broadcast({"type": "update", **to_json(m)})


@client.event
async def on_message(m: discord.Message):
    broadcast({"type": "new", **to_json(m)})


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
    async with client:
        await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())

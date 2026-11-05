"""Bot Discord + interface web pour lire les salons sans être sur le serveur."""
import asyncio
import base64
import hmac
import json
import os
from pathlib import Path

import discord
from aiohttp import web

TOKEN = os.environ.get("DISCORD_TOKEN", "")
PASSWORD = os.environ.get("VIEWER_PASSWORD", "")
PORT = int(os.environ.get("PORT", "8080"))
HTML = Path(__file__).with_name("index.html")

intents = discord.Intents.default()
intents.message_content = True  # à activer aussi dans le Developer Portal
client = discord.Client(intents=intents)
listeners: set[asyncio.Queue] = set()


def to_json(m: discord.Message) -> dict:
    return {
        "id": str(m.id),
        "channel": str(m.channel.id),
        "author": m.author.display_name,
        "avatar": m.author.display_avatar.url,
        "bot": m.author.bot,
        "content": m.clean_content,
        "time": m.created_at.isoformat(),
        "attachments": [a.url for a in m.attachments],
    }


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
    if not password_ok(request.headers.get("Authorization", ""), PASSWORD):
        return web.Response(status=401, headers={"WWW-Authenticate": 'Basic realm="viewer"'})
    return await handler(request)


async def index(_):
    return web.FileResponse(HTML)


async def channels(_):
    out = []
    for g in client.guilds:
        for c in g.text_channels:
            perms = c.permissions_for(g.me)
            if perms.view_channel and perms.read_message_history:
                out.append({"id": str(c.id), "name": f"{g.name} / #{c.name}"})
    return web.json_response(out)


async def messages(request):
    try:
        channel = client.get_channel(int(request.match_info["id"]))
        before = request.query.get("before")
        before = discord.Object(int(before)) if before else None
    except ValueError:
        raise web.HTTPBadRequest()
    if not isinstance(channel, discord.TextChannel):
        raise web.HTTPNotFound()
    # Historique complet possible, y compris avant l'arrivée du bot (paquets de 50).
    msgs = [to_json(m) async for m in channel.history(limit=50, before=before)]
    return web.json_response(msgs[::-1])


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


@client.event
async def on_message(m: discord.Message):
    data = to_json(m)
    for q in list(listeners):
        if not q.full():
            q.put_nowait(data)


async def main():
    if not TOKEN or not PASSWORD:
        raise SystemExit("Définis DISCORD_TOKEN et VIEWER_PASSWORD.")
    app = web.Application(middlewares=[auth])
    app.add_routes([
        web.get("/", index),
        web.get("/api/channels", channels),
        web.get("/api/channels/{id}/messages", messages),
        web.get("/api/stream", stream),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    print(f"Interface sur http://localhost:{PORT}")
    async with client:
        await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())

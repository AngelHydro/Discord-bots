import base64

import os
import tempfile
from pathlib import Path

from autostart import vbs_content
from types import SimpleNamespace as NS

import discord

from bot import PUBLIC, activity_text, group_members, load_env, matches, password_ok, should_notify


def h(s):
    return "Basic " + base64.b64encode(s.encode()).decode()


assert password_ok(h("x:secret"), "secret")
assert password_ok(h(":a:b"), "a:b")
assert not password_ok(h("x:nope"), "secret")
assert not password_ok(h("x:"), "")  # pas de mot de passe configuré = refus
assert not password_ok("Bearer abc", "secret")
assert not password_ok("Basic !!!", "secret")
msg = {"author": "Alice", "text": "Rendez-vous Demain"}
assert matches(msg, "demain")
assert matches(msg, "ALI")
assert not matches(msg, "bob")
with tempfile.TemporaryDirectory() as d:
    env = Path(d) / ".env"
    env.write_text('# commentaire\nT_A="abc=1"\nT_B = x \nvide\n', encoding="utf-8")
    os.environ["T_B"] = "garde"
    load_env(env)
    assert os.environ["T_A"] == "abc=1"
    assert os.environ["T_B"] == "garde"  # une variable déjà définie n'est pas écrasée
    load_env(Path(d) / "absent")  # fichier manquant : pas d'erreur
vbs = vbs_content(Path(r"C:\Users\a b\Discord-bots"), r"C:\Py 3\python.exe")
# Guillemets doublés pour VBScript, chemins avec espaces protégés, fenêtre cachée (0).
assert vbs == (
    r'CreateObject("WScript.Shell").Run "cmd /c cd /d ""C:\Users\a b\Discord-bots"" && '
    r'""C:\Py 3\python.exe"" -u viewer\bot.py > viewer.log 2>&1", 0' "\r\n"
), vbs
assert "/" not in PUBLIC and not any(p.startswith("/api") for p in PUBLIC)  # les données restent protégées
# Notifications : salon (nom, ID ou salon parent d'un fil) ET mots-clés
n = ["mon-fil", "annonces"], ["11", "22"]
assert should_notify(*n, "Salut", set(), [])
assert should_notify(*n, "Salut", {"annonces"}, [])  # via le salon parent
assert should_notify(*n, "Salut", {"11"}, [])
assert not should_notify(*n, "Salut", {"général"}, [])
assert should_notify(*n, "Soirée DEMAIN", set(), ["demain"])
assert not should_notify(*n, "Salut", set(), ["demain"])
assert not should_notify(*n, "demain", {"général"}, ["demain"])
# Activité : la vraie activité passe avant le statut perso ; Spotify affiche titre — artiste
A = discord.ActivityType
custom = NS(type=A.custom, emoji="🔥", state="En vacances", name="Custom Status")
assert activity_text([custom]) == "🔥 En vacances"
assert activity_text([custom, NS(type=A.playing, name="Minecraft")]) == "Joue à Minecraft"
assert activity_text([NS(type=A.listening, name="Spotify", title="Titre", artist="Artiste")]) == "Écoute Titre — Artiste"
assert activity_text([NS(type=A.custom, emoji=NS(id=1, name="perso"), state="ok", name="")]) == "ok"
assert activity_text([]) == ""

# Groupes : rôles affichés (du plus haut au plus bas) > En ligne > Hors ligne ; tri alphabétique
row = lambda name, status, hoist=None: {"name": name, "status": status, "hoist": hoist}
g = group_members([
    row("zoé", "online"), row("Bob", "offline", (5, "Admin")), row("alice", "idle"),
    row("Max", "dnd", (5, "Admin")), row("Léo", "online", (2, "Modo")), row("Cal", "offline"),
])
assert [(x["name"], x["count"], [m["name"] for m in x["members"]]) for x in g] == [
    ("Admin", 1, ["Max"]), ("Modo", 1, ["Léo"]), ("En ligne", 2, ["alice", "zoé"]), ("Hors ligne", 2, ["Bob", "Cal"]),
], g
print("ok")

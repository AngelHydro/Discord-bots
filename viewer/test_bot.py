import base64

import os
import tempfile
from pathlib import Path

from autostart import vbs_content
from bot import PUBLIC, load_env, matches, password_ok, should_notify


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
print("ok")

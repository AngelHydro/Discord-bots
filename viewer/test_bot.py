import base64

import os
import tempfile
from pathlib import Path

from bot import load_env, matches, password_ok


def h(s):
    return "Basic " + base64.b64encode(s.encode()).decode()


assert password_ok(h("x:secret"), "secret")
assert password_ok(h(":a:b"), "a:b")
assert not password_ok(h("x:nope"), "secret")
assert not password_ok(h("x:"), "")  # pas de mot de passe configuré = refus
assert not password_ok("Bearer abc", "secret")
assert not password_ok("Basic !!!", "secret")
msg = {"author": "Alice", "content": "Rendez-vous Demain"}
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
print("ok")

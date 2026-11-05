import base64

from bot import matches, password_ok


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
print("ok")

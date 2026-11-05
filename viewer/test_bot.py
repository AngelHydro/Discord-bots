import base64

from bot import password_ok


def h(s):
    return "Basic " + base64.b64encode(s.encode()).decode()


assert password_ok(h("x:secret"), "secret")
assert password_ok(h(":a:b"), "a:b")
assert not password_ok(h("x:nope"), "secret")
assert not password_ok(h("x:"), "")  # pas de mot de passe configuré = refus
assert not password_ok("Bearer abc", "secret")
assert not password_ok("Basic !!!", "secret")
print("ok")

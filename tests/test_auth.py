import threading
from collections import OrderedDict

from simple_webdav import auth
from simple_webdav.auth import ConfigDomainController


def make_controller(monkeypatch, *, readonly=False):
    controller = ConfigDomainController.__new__(ConfigDomainController)
    controller.users = {
        "teacher": {
            "password_hash": "fake-bcrypt-hash",
            "readonly": readonly,
        }
    }
    controller._success_cache = OrderedDict()
    controller._cache_lock = threading.Lock()
    calls = []

    def checkpw(password, password_hash):
        calls.append((password, password_hash))
        return password == b"correct" and password_hash == b"fake-bcrypt-hash"

    monkeypatch.setattr(auth.bcrypt, "checkpw", checkpw)
    return controller, calls


def test_successful_bcrypt_authentication_is_cached(monkeypatch):
    controller, calls = make_controller(monkeypatch)
    first_env = {}
    second_env = {}

    assert controller.basic_auth_user("", "teacher", "correct", first_env)
    assert controller.basic_auth_user("", "teacher", "correct", second_env)

    assert len(calls) == 1
    assert first_env["wsgidav.auth.roles"] == ("editor",)
    assert second_env["wsgidav.auth.roles"] == ("editor",)


def test_failed_password_is_not_cached(monkeypatch):
    controller, calls = make_controller(monkeypatch)

    assert not controller.basic_auth_user("", "teacher", "wrong", {})
    assert not controller.basic_auth_user("", "teacher", "wrong", {})

    assert len(calls) == 2


def test_authentication_cache_expires(monkeypatch):
    controller, calls = make_controller(monkeypatch)
    now = [100.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: now[0])

    assert controller.basic_auth_user("", "teacher", "correct", {})
    assert controller.basic_auth_user("", "teacher", "correct", {})
    now[0] += controller.AUTH_CACHE_TTL_SECONDS + 0.1
    assert controller.basic_auth_user("", "teacher", "correct", {})

    assert len(calls) == 2


def test_cached_authentication_uses_current_readonly_role(monkeypatch):
    controller, calls = make_controller(monkeypatch, readonly=True)

    first_env = {}
    second_env = {}
    assert controller.basic_auth_user("", "teacher", "correct", first_env)
    controller.users["teacher"]["readonly"] = False
    assert controller.basic_auth_user("", "teacher", "correct", second_env)

    assert len(calls) == 1
    assert first_env["wsgidav.auth.roles"] == ("reader",)
    assert second_env["wsgidav.auth.roles"] == ("editor",)

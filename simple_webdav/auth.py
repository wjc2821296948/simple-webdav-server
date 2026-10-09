from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict

import bcrypt
from wsgidav.dc.base_dc import BaseDomainController


class ConfigDomainController(BaseDomainController):
    """Authenticate users from the application's YAML configuration."""

    AUTH_CACHE_TTL_SECONDS = 60.0
    AUTH_CACHE_MAX_ENTRIES = 2048

    def __init__(self, wsgidav_app, config):
        super().__init__(wsgidav_app, config)
        section = config.get("simple_webdav", {})
        self.users = section.get("users", {})
        if not isinstance(self.users, dict) or not self.users:
            raise ValueError("simple_webdav.users must contain at least one user")
        # Cache only successful bcrypt checks. The password itself is never
        # retained; the cache key contains a one-way digest instead.
        self._success_cache = OrderedDict()
        self._cache_lock = threading.Lock()

    def get_domain_realm(self, path_info, environ):
        return self._calc_realm_from_path_provider(path_info, environ)

    def require_authentication(self, realm, environ):
        return True

    def basic_auth_user(self, realm, user_name, password, environ):
        user = self.users.get(user_name)
        if not user:
            return False

        password_hash = user.get("password_hash")
        plain_password = user.get("password")

        if password_hash:
            password_bytes = password.encode("utf-8")
            cache_key = (
                user_name,
                password_hash,
                hashlib.sha256(password_bytes).digest(),
            )
            now = time.monotonic()
            with self._cache_lock:
                expires_at = self._success_cache.get(cache_key)
                if expires_at is not None and expires_at > now:
                    self._success_cache.move_to_end(cache_key)
                    environ["wsgidav.auth.roles"] = (
                        ("reader",) if user.get("readonly", False) else ("editor",)
                    )
                    return True
                if expires_at is not None:
                    self._success_cache.pop(cache_key, None)

            try:
                valid = bcrypt.checkpw(
                    password_bytes,
                    password_hash.encode("utf-8"),
                )
            except ValueError:
                valid = False

            if valid:
                expires_at = time.monotonic() + self.AUTH_CACHE_TTL_SECONDS
                with self._cache_lock:
                    self._success_cache[cache_key] = expires_at
                    self._success_cache.move_to_end(cache_key)
                    while len(self._success_cache) > self.AUTH_CACHE_MAX_ENTRIES:
                        self._success_cache.popitem(last=False)
        elif plain_password is not None:
            valid = password == str(plain_password)
        else:
            valid = False

        if valid:
            environ["wsgidav.auth.roles"] = (
                ("reader",) if user.get("readonly", False) else ("editor",)
            )
            return True

        return False

    def supports_http_digest_auth(self):
        return False

from __future__ import annotations

import bcrypt
from wsgidav.dc.base_dc import BaseDomainController


class ConfigDomainController(BaseDomainController):
    """Authenticate users from the application's YAML configuration."""

    def __init__(self, wsgidav_app, config):
        super().__init__(wsgidav_app, config)
        section = config.get("simple_webdav", {})
        self.users = section.get("users", {})
        if not isinstance(self.users, dict) or not self.users:
            raise ValueError("simple_webdav.users must contain at least one user")

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
            try:
                valid = bcrypt.checkpw(
                    password.encode("utf-8"),
                    password_hash.encode("utf-8"),
                )
            except ValueError:
                valid = False
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

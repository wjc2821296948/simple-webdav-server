from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

from wsgidav import util
from wsgidav.dav_error import DAVError, HTTP_FORBIDDEN, HTTP_LENGTH_REQUIRED
from wsgidav.fs_dav_provider import (
    BUFFER_SIZE,
    FileResource,
    FilesystemProvider,
    FolderResource,
)


def parse_size(value) -> int | None:
    """Parse a human-readable byte value such as 2GiB or 500MiB."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("quota must be a size, not a boolean")
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip().lower().replace(" ", "")
    units = {
        "b": 1,
        "kb": 1000,
        "kib": 1024,
        "mb": 1000**2,
        "mib": 1024**2,
        "gb": 1000**3,
        "gib": 1024**3,
        "tb": 1000**4,
        "tib": 1024**4,
    }

    for suffix in sorted(units, key=len, reverse=True):
        if text.endswith(suffix):
            number = text[: -len(suffix)]
            return int(float(number) * units[suffix])

    return int(text)


class UserFilesystemProvider(FilesystemProvider):
    """One WebDAV root that is dynamically chrooted per authenticated user."""

    def __init__(self, data_root: str, users: dict):
        self.data_root = Path(data_root).resolve()
        self.data_root.mkdir(parents=True, exist_ok=True)

        if not isinstance(users, dict) or not users:
            raise ValueError("users must be a non-empty mapping")

        self.users = {}
        for username, raw in users.items():
            if not isinstance(raw, dict):
                raise ValueError(f"user {username!r} must be a mapping")

            root = Path(str(raw.get("root", username)))
            if not root.is_absolute():
                root = self.data_root / root
            root = root.resolve()

            if os.path.commonpath((str(self.data_root), str(root))) != str(self.data_root):
                raise ValueError(f"user root escapes data_root: {username!r}")

            root.mkdir(parents=True, exist_ok=True)

            self.users[str(username)] = {
                "root": root,
                "readonly": bool(raw.get("readonly", False)),
                "quota": parse_size(raw.get("quota")),
            }

        # FilesystemProvider supplies the path-safety and provider machinery.
        super().__init__(str(self.data_root), readonly=False, fs_opts={})
        self._quota_locks = {
            username: threading.RLock() for username in self.users
        }

    def _get_user(self, environ):
        username = environ.get("wsgidav.auth.user_name")
        if username not in self.users:
            raise DAVError(HTTP_FORBIDDEN, "Unknown WebDAV user")
        return username

    def _user_root(self, environ):
        return self.users[self._get_user(environ)]["root"]

    def _user_config(self, environ):
        return self.users[self._get_user(environ)]

    def is_readonly(self):
        # RequestServer creates its method table once, so this provider must
        # advertise write support globally. Read-only users are enforced by
        # the resource objects below.
        return False

    def _loc_to_file_path(self, path: str, environ: dict | None = None):
        root_path = self._user_root(environ)
        path_parts = path.strip("/").split("/") if path.strip("/") else []
        file_path = os.path.abspath(os.path.join(root_path, *path_parts))

        if not self.fs_opts.get("follow_symlinks"):
            is_in_root = self._is_equal_or_child_path(
                str(root_path), os.path.realpath(file_path)
            )
        else:
            is_in_root = self._is_equal_or_child_path(str(root_path), file_path)

        if not is_in_root:
            raise DAVError(HTTP_FORBIDDEN, "Access outside user root is not allowed")

        return util.to_unicode_safe(file_path)

    def used_bytes(self, environ):
        root = self._user_root(environ)
        total = 0
        for current_root, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(current_root, d))]
            for filename in files:
                path = os.path.join(current_root, filename)
                if os.path.islink(path):
                    continue
                try:
                    total += os.path.getsize(path)
                except FileNotFoundError:
                    continue
        return total

    def check_quota(self, environ, path: str, incoming_size: int):
        quota = self._user_config(environ)["quota"]
        if quota is None:
            return

        current_path = self._loc_to_file_path(path, environ)
        existing_size = os.path.getsize(current_path) if os.path.isfile(current_path) else 0

        with self._quota_locks[self._get_user(environ)]:
            used = self.used_bytes(environ)
            projected = used - existing_size + incoming_size
            if projected > quota:
                raise DAVError(
                    507,
                    f"Quota exceeded: {projected} > {quota} bytes",
                )

    def get_resource_inst(self, path: str, environ: dict):
        self._count_get_resource_inst += 1
        fp = self._loc_to_file_path(path, environ)

        if not os.path.exists(fp):
            return None
        if not self.fs_opts.get("follow_symlinks") and os.path.islink(fp):
            raise DAVError(HTTP_FORBIDDEN, "Symlink support is disabled")

        if os.path.isdir(fp):
            return UserFolderResource(path, environ, fp)
        return UserFileResource(path, environ, fp)


class UserFileResource(FileResource):
    def _user_config(self):
        return self.provider._user_config(self.environ)

    def begin_write(self, *, content_type=None):
        cfg = self._user_config()
        if cfg["readonly"]:
            raise DAVError(HTTP_FORBIDDEN)

        content_length = self.environ.get("CONTENT_LENGTH")
        if content_length in (None, ""):
            raise DAVError(
                HTTP_LENGTH_REQUIRED,
                "PUT requests must include Content-Length for quota enforcement",
            )

        try:
            incoming_size = int(content_length)
        except ValueError as exc:
            raise DAVError(HTTP_LENGTH_REQUIRED, "Invalid Content-Length") from exc

        self.provider.check_quota(self.environ, self.path, incoming_size)
        return open(self._file_path, "wb", BUFFER_SIZE)

    def delete(self):
        if self._user_config()["readonly"]:
            raise DAVError(HTTP_FORBIDDEN)
        return super().delete()

    def copy_move_single(self, dest_path, *, is_move):
        if self._user_config()["readonly"]:
            raise DAVError(HTTP_FORBIDDEN)

        if not is_move:
            dest_fp = self.provider._loc_to_file_path(dest_path, self.environ)
            source_size = os.path.getsize(self._file_path)
            old_dest_size = os.path.getsize(dest_fp) if os.path.isfile(dest_fp) else 0
            quota = self._user_config()["quota"]
            if quota is not None:
                with self.provider._quota_locks[self.provider._get_user(self.environ)]:
                    used = self.provider.used_bytes(self.environ)
                    if used - old_dest_size + source_size > quota:
                        raise DAVError(507, "Quota exceeded by COPY")

        return super().copy_move_single(dest_path, is_move=is_move)


class UserFolderResource(FolderResource):
    def _user_config(self):
        return self.provider._user_config(self.environ)

    def get_used_bytes(self):
        return self.provider.used_bytes(self.environ)

    def get_available_bytes(self):
        quota = self._user_config()["quota"]
        if quota is None:
            return shutil.disk_usage(self._file_path).free
        return max(0, quota - self.provider.used_bytes(self.environ))

    def create_empty_resource(self, name):
        if self._user_config()["readonly"]:
            raise DAVError(HTTP_FORBIDDEN)

        content_length = self.environ.get("CONTENT_LENGTH")
        if content_length in (None, ""):
            raise DAVError(
                HTTP_LENGTH_REQUIRED,
                "PUT requests must include Content-Length for quota enforcement",
            )

        try:
            incoming_size = int(content_length)
        except ValueError as exc:
            raise DAVError(HTTP_LENGTH_REQUIRED, "Invalid Content-Length") from exc

        new_path = f"{self.path.rstrip('/')}/{name}"
        self.provider.check_quota(self.environ, new_path, incoming_size)
        return super().create_empty_resource(name)

    def create_collection(self, name):
        if self._user_config()["readonly"]:
            raise DAVError(HTTP_FORBIDDEN)
        return super().create_collection(name)

    def delete(self):
        if self._user_config()["readonly"]:
            raise DAVError(HTTP_FORBIDDEN)
        return super().delete()

    def copy_move_single(self, dest_path, *, is_move):
        if self._user_config()["readonly"]:
            raise DAVError(HTTP_FORBIDDEN)
        # Recursive directory COPY is intentionally not special-cased in v0.1;
        # ordinary file COPY still receives quota enforcement.
        if not is_move:
            raise DAVError(
                405,
                "Directory COPY is not implemented in the first version",
            )
        return super().copy_move_single(dest_path, is_move=is_move)

    def move_recursive(self, dest_path):
        if self._user_config()["readonly"]:
            raise DAVError(HTTP_FORBIDDEN)
        return super().move_recursive(dest_path)

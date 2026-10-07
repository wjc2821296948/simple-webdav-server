from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path

import yaml
from wsgidav.default_conf import DEFAULT_CONFIG
from wsgidav.server.server_cli import _run_cheroot
from wsgidav.wsgidav_app import WsgiDAVApp

from .provider import UserFilesystemProvider


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    users = raw.get("users")
    if not isinstance(users, dict) or not users:
        raise ValueError("config.yaml must define a non-empty users mapping")

    data_root = raw.get("data_root", "./data")
    if not os.path.isabs(data_root):
        data_root = str((Path(path).parent / data_root).resolve())

    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update({
        "host": raw.get("host", "0.0.0.0"),
        "port": int(raw.get("port", 8080)),
        "verbose": int(raw.get("verbose", 3)),
        "dir_browser": {
            "enable": bool(raw.get("dir_browser", {}).get("enable", True)),
        },
        "http_authenticator": {
            "accept_basic": True,
            "accept_digest": False,
            "default_to_digest": False,
            "domain_controller": "simple_webdav.auth.ConfigDomainController",
        },
        "simple_webdav": {
            "users": users,
        },
        "provider_mapping": {
            "/": UserFilesystemProvider(data_root, users),
        },
    })

    # Keep useful low-memory defaults and allow explicitly supported WsgiDAV
    # settings from the YAML file without exposing provider internals.
    for key in ("block_size", "hotfixes", "server_args"):
        if key in raw:
            config[key] = raw[key]

    return config


def main():
    parser = argparse.ArgumentParser(description="Simple config-driven WebDAV server")
    parser.add_argument(
        "-c",
        "--config",
        default=os.environ.get("SIMPLE_WEBDAV_CONFIG", "config.yaml"),
    )
    args = parser.parse_args()

    config = load_config(args.config)
    app = WsgiDAVApp(config)
    _run_cheroot(app, app.config, "cheroot")


if __name__ == "__main__":
    main()

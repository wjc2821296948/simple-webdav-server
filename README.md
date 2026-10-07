# Simple WebDAV Server

A lightweight, config-driven WebDAV server for small deployments.

The project uses [WsgiDAV](https://github.com/mar10/wsgidav) for the WebDAV protocol and keeps the application layer intentionally small.

## Features

- YAML-only configuration
- Per-user isolated filesystem roots
- Per-user read-only/read-write access
- Per-user storage quotas
- HTTP Basic authentication
- WebDAV directory browser
- Docker deployment
- No database and no management panel

## Configuration

Copy `config.example.yaml` to `config.yaml` and edit the users.

For passwords, `password_hash` is preferred. Generate a bcrypt hash with:

```bash
docker compose run --rm webdav python -m simple_webdav.hash_password
```

Then put the generated value into `config.yaml`.

The `root` value is relative to `data_root` unless it is an absolute path.

Example:

```yaml
data_root: /data

users:
  display:
    root: display
    readonly: true
    quota: 5GiB
    password_hash: "$2b$..."

  math:
    root: math
    readonly: false
    quota: 2GiB
    password_hash: "$2b$..."
```

The authenticated user always sees `/` as their own root. A user cannot browse another user's configured directory.

## Running with Docker

```bash
cp config.example.yaml config.yaml
# edit config.yaml
mkdir -p data
docker compose up -d --build
```

The WebDAV endpoint is:

```
http://HOST:8080/
```

Put the service behind HTTPS, Cloudflare Tunnel, or another trusted TLS reverse proxy before exposing it publicly.

## Storage quotas

Quotas are enforced for PUT uploads using the request's Content-Length and are reported through standard WebDAV quota properties.

The first version deliberately keeps quota accounting filesystem-based and has no database. This is intended for small deployments with low concurrency.

For the same reason, directory COPY is not implemented in v0.1. File COPY is supported and checked against the user's quota. MOVE/rename remains supported.

## Security

Do not expose plain HTTP Basic authentication directly to the Internet.

Keep `config.yaml` private and give it restrictive filesystem permissions.

## License

Apache-2.0.

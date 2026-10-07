# Simple WebDAV Server

A lightweight, config-driven WebDAV server for small deployments.

The project uses WsgiDAV for the WebDAV protocol and keeps the application layer intentionally small.

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

## Running

```bash
cp config.example.yaml config.yaml
docker compose up -d
```

The WebDAV endpoint is:

```
http://HOST:8080/
```

Put the service behind HTTPS, Cloudflare Tunnel, or another trusted TLS reverse proxy before exposing it publicly.

## Storage quotas

Quotas are enforced for PUT uploads using the request's Content-Length and are reported through standard WebDAV quota properties.

## Security

Do not expose plain HTTP Basic authentication directly to the Internet.

Keep `config.yaml` private and give it restrictive filesystem permissions.

## License

Apache-2.0.

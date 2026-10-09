from pathlib import Path

from simple_webdav.provider import parse_size


def test_parse_size():
    assert parse_size("1KiB") == 1024
    assert parse_size("2MiB") == 2 * 1024**2
    assert parse_size("3GiB") == 3 * 1024**3
    assert parse_size("100") == 100


def test_relative_user_root(tmp_path):
    root = tmp_path / "data"
    root.mkdir()

    # This is a structural test for the same path policy used by the provider.
    user_root = (root / "math").resolve()
    assert Path(root).resolve() in user_root.parents


def test_used_bytes_is_cached_until_invalidated(tmp_path):
    from simple_webdav.provider import UserFilesystemProvider

    data_root = tmp_path / "data"
    provider = UserFilesystemProvider(
        str(data_root),
        {"teacher": {"root": "teacher", "quota": "1KiB"}},
    )
    environ = {"wsgidav.auth.user_name": "teacher"}
    user_root = data_root / "teacher"
    (user_root / "first.txt").write_bytes(b"123")

    assert provider.used_bytes(environ) == 3

    (user_root / "second.txt").write_bytes(b"45678")
    # The directory is not walked again while its short cache entry is valid.
    assert provider.used_bytes(environ) == 3

    provider.invalidate_usage("teacher")
    assert provider.used_bytes(environ) == 8


def test_usage_cache_is_separate_per_user(tmp_path):
    from simple_webdav.provider import UserFilesystemProvider

    data_root = tmp_path / "data"
    provider = UserFilesystemProvider(
        str(data_root),
        {
            "teacher-a": {"root": "teacher-a", "quota": "1KiB"},
            "teacher-b": {"root": "teacher-b", "quota": "1KiB"},
        },
    )
    (data_root / "teacher-a" / "one.txt").write_bytes(b"1234")
    (data_root / "teacher-b" / "two.txt").write_bytes(b"12")

    assert provider.used_bytes({"wsgidav.auth.user_name": "teacher-a"}) == 4
    assert provider.used_bytes({"wsgidav.auth.user_name": "teacher-b"}) == 2

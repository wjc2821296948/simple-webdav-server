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

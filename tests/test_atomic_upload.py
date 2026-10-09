import pytest

from wsgidav.dav_error import DAVError

from simple_webdav.provider import UserFilesystemProvider


def make_provider(tmp_path, quota="1KiB"):
    data_root = tmp_path / "data"
    provider = UserFilesystemProvider(
        str(data_root),
        {"teacher": {"root": "teacher", "quota": quota}},
    )
    environ = {"wsgidav.auth.user_name": "teacher", "CONTENT_LENGTH": "0"}
    environ["wsgidav.provider"] = provider
    return provider, environ, data_root / "teacher"


def temp_uploads(root):
    return list(root.rglob(".simple-webdav-upload-*.tmp"))


def test_new_file_is_published_only_after_upload_completes(tmp_path):
    provider, environ, root_path = make_provider(tmp_path)
    environ["CONTENT_LENGTH"] = "6"
    root_resource = provider.get_resource_inst("/", environ)

    resource = root_resource.create_empty_resource("lesson.bin")
    target_path = root_path / "lesson.bin"
    assert not target_path.exists()
    assert root_resource.get_member_names() == []

    writer = resource.begin_write()
    writer.writelines([b"abc", b"def"])
    writer.close()
    resource.end_write(with_errors=False)

    assert target_path.read_bytes() == b"abcdef"
    assert temp_uploads(root_path) == []
    assert provider._upload_reservations["teacher"] == {}


def test_interrupted_overwrite_preserves_original_file(tmp_path):
    provider, environ, root_path = make_provider(tmp_path)
    target_path = root_path / "lesson.bin"
    target_path.write_bytes(b"original")
    environ["CONTENT_LENGTH"] = "5"
    resource = provider.get_resource_inst("/lesson.bin", environ)

    writer = resource.begin_write()
    writer.write(b"part")
    writer.close()
    resource.end_write(with_errors=True)

    assert target_path.read_bytes() == b"original"
    assert temp_uploads(root_path) == []
    assert provider._upload_reservations["teacher"] == {}


def test_failed_new_upload_leaves_no_empty_destination(tmp_path):
    provider, environ, root_path = make_provider(tmp_path)
    environ["CONTENT_LENGTH"] = "8"
    root_resource = provider.get_resource_inst("/", environ)
    resource = root_resource.create_empty_resource("incomplete.bin")
    target_path = root_path / "incomplete.bin"

    writer = resource.begin_write()
    writer.write(b"partial")
    writer.close()
    resource.end_write(with_errors=True)

    assert not target_path.exists()
    assert temp_uploads(root_path) == []
    assert provider._upload_reservations["teacher"] == {}


def test_concurrent_upload_reservations_enforce_quota(tmp_path):
    provider, environ, root_path = make_provider(tmp_path, quota="10B")
    root_resource = provider.get_resource_inst("/", environ)

    environ["CONTENT_LENGTH"] = "6"
    first = root_resource.create_empty_resource("first.bin")
    first_writer = first.begin_write()
    first_writer.write(b"123456")

    environ["CONTENT_LENGTH"] = "5"
    second = root_resource.create_empty_resource("second.bin")
    with pytest.raises(DAVError):
        second.begin_write()

    first_writer.close()
    first.end_write(with_errors=True)
    assert temp_uploads(root_path) == []
    assert provider._upload_reservations["teacher"] == {}


def test_content_length_mismatch_does_not_replace_existing_file(tmp_path):
    provider, environ, root_path = make_provider(tmp_path)
    target_path = root_path / "lesson.bin"
    target_path.write_bytes(b"old")
    environ["CONTENT_LENGTH"] = "5"
    resource = provider.get_resource_inst("/lesson.bin", environ)

    writer = resource.begin_write()
    writer.write(b"new")
    writer.close()
    with pytest.raises(DAVError):
        resource.end_write(with_errors=False)

    assert target_path.read_bytes() == b"old"
    assert temp_uploads(root_path) == []
    assert provider._upload_reservations["teacher"] == {}

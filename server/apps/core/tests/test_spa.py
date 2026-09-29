import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db


@pytest.fixture
def built(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    with override_settings(SPA_ROOT=tmp_path):
        yield tmp_path


def test_client_routes_get_index_html(client, built):
    for path in ("/", "/stays/1234", "/print/invoice/abc", "/settings/users"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert b'<div id="root">' in b"".join(res.streaming_content)
        assert res["Cache-Control"] == "no-cache"
        assert "script-src 'self'" in res["Content-Security-Policy"]  # C-12 / E-14


def test_assets_are_cached_and_top_level_files_served(client, built):
    res = client.get("/assets/index-abc123.js")
    assert res.status_code == 200
    assert res["Cache-Control"] == "public, max-age=31536000, immutable"
    assert client.get("/favicon.svg").status_code == 200
    assert client.get("/assets/missing.js").status_code == 404


def test_api_paths_are_not_swallowed_by_the_spa(client, built):
    res = client.get("/api/v1/nope")
    assert res.status_code == 404
    assert res["Content-Type"].startswith("application/json")
    assert res.json() == {"code": "not_found", "detail": "العنصر غير موجود."}


def test_no_build_yet_explains_what_to_do(client, tmp_path):
    with override_settings(SPA_ROOT=tmp_path):
        res = client.get("/")
    assert res.status_code == 503
    assert "build_spa.py" in res.content.decode()


def test_paths_outside_the_build_are_refused(client, built):
    res = client.get("/..%2F..%2Fetc%2Fpasswd")
    assert res.status_code == 200  # falls back to the SPA, never a file outside the root
    assert b'<div id="root">' in b"".join(res.streaming_content)

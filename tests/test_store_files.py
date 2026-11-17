"""Store Files Separately: the whole batch is checked before a byte is stored, types come from the bytes, names may
be non-ASCII, downloads can't run as the site, and a signed-out download is a 404."""

from pathlib import Path

from tests.conftest import Api, start_app

PNG = (Path(__file__).parent.parent / "shared" / "samples" / "work-order-scan.png").read_bytes()
PDF = b"%PDF-1.4\n% Demo receipt\n%%EOF\n"
HTML = b"<!DOCTYPE html><script>alert(document.cookie)</script>"
BIG = PNG + b"\0" * (5 * 1024 * 1024)


def upload(api: Api, *files: tuple[str, bytes, str], field: str = "files[]") -> object:
    return api.post("/api/files", files=[(field, (name, content, type)) for name, content, type in files])


def stored_files(api: Api) -> int:
    return api.count("files")


def test_a_batch_is_stored_in_order_and_downloads_the_same_bytes(api: Api) -> None:
    r = upload(api, ("one.pdf", PDF, "application/pdf"), ("two.png", PNG, "image/png"))
    assert r.status_code == 200
    ids = r.json()
    assert len(ids) == 2 and all(isinstance(id, str) and id for id in ids)
    for id, content, type in ((ids[0], PDF, "application/pdf"), (ids[1], PNG, "image/png")):
        d = api.get(f"/api/files/{id}")
        assert (d.status_code, d.content, d.headers["content-type"]) == (200, content, type)
        assert not (api.settings.files_dir / id).with_suffix(".png").exists()   # stored by id, no extension


def test_one_bad_file_refuses_the_whole_batch(api: Api) -> None:
    before = stored_files(api)
    for files, message in (
        ([("ok.png", PNG, "image/png"), ("page.png", HTML, "image/png")], "page.png is not a PNG, JPEG, WebP, GIF or PDF file"),
        ([("ok.png", PNG, "image/png"), ("big.png", BIG, "image/png")], "Each file must be 5 MB or less"),
    ):
        r = upload(api, *files)
        assert (r.status_code, r.json()) == (422, {"error": message})
    r = upload(api, ("ok.png", PNG, "image/png"), field="files")   # PHP keeps only the last of several "files"
    assert (r.status_code, r.json()) == (422, {"error": 'Upload one or more files in a field named "files[]"'})
    assert stored_files(api) == before


def test_the_type_comes_from_the_bytes_and_the_name_may_be_cyrillic(api: Api) -> None:
    [id] = upload(api, ("квитанция.png", PNG, "text/html")).json()
    with api.db() as conn:
        row = conn.execute("SELECT name, type FROM files WHERE id = ?", (id,)).fetchone()
    assert (row["name"], row["type"]) == ("квитанция.png", "image/png")


def test_an_html_file_is_served_with_nosniff_and_sandbox(api: Api) -> None:
    # The upload refuses HTML, so put one in place the way another code path might have stored it
    with api.db() as conn:
        conn.execute("INSERT INTO files (id, name, type) VALUES ('html-file', 'page.html', 'text/html')")
    (api.settings.files_dir / "html-file").write_bytes(HTML)
    d = api.get("/api/files/html-file")
    assert d.status_code == 200 and d.headers["content-type"].startswith("text/html")
    assert d.headers["x-content-type-options"] == "nosniff"
    assert d.headers["content-security-policy"] == "sandbox"


def test_signed_out_and_unknown_downloads_answer_404(api: Api) -> None:
    [id] = upload(api, ("a.png", PNG, "image/png")).json()
    assert (api.get(f"/api/files/{id}", user=None).status_code, api.get(f"/api/files/{id}", user=None).json()) == \
        (404, {"error": "Not found"})
    assert api.get("/api/files/no-such-file").status_code == 404


def test_the_demo_caps_every_upload_at_5_mb_first(tmp_path: Path) -> None:
    with start_app(tmp_path, demo_mode=True) as api:
        api.get("/up")
        r = upload(api, ("page.png", HTML, "image/png"), ("big.png", BIG, "image/png"))
        assert (r.status_code, r.json()) == (413, {"error": "Files over 5 MB are not accepted on the demo"})
        r = api.post("/api/work-orders/extract", files={"scan": ("big.png", BIG, "image/png")})
        assert (r.status_code, r.json()) == (413, {"error": "Files over 5 MB are not accepted on the demo"})
        r = upload(api, ("ok.png", PNG, "image/png"), ("page.png", HTML, "image/png"))
        assert r.status_code == 422
        r = upload(api, ("ok.png", PNG, "image/png"))
        assert r.status_code == 200
        [id] = r.json()
        assert (api.settings.sandbox_dir / api.sid / id).is_file()   # the visitor's uploads folder

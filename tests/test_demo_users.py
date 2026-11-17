"""The demo users: each page signs in as a user it offers, the API reads the cookie as it is, Bob's saves answer
403 with the edit-forms message, and signed out the progress endpoints answer 401."""

from tests.conftest import Api, page_config


def demo_user_cookie(r: object) -> str | None:
    return next((line for line in r.headers.get_list("set-cookie") if line.startswith("demo_user=")), None)


def test_a_page_that_offers_the_user_keeps_it_any_other_signs_in_as_its_default(api: Api) -> None:
    kept = api.get("/examples/resume-progress", user="bob")
    assert page_config(kept.text)["demoUser"] == "bob"
    assert demo_user_cookie(kept) is None

    reset = api.get("/examples/save-response", user="bob")
    assert page_config(reset.text)["demoUser"] == "alice"
    cookie = demo_user_cookie(reset)
    assert cookie is not None and cookie.startswith("demo_user=alice;")
    assert "samesite=lax" in cookie.lower() and "httponly" not in cookie.lower()   # host.js writes it back on focus

    assert page_config(api.get("/examples/creator-load-save", user="none").text)["demoUser"] == "alice"
    assert page_config(api.get("/examples/dashboard", user=None).text)["user"]["name"] == "Alice Martin"


def test_claim_signs_in_like_its_example_page(api: Api) -> None:
    assert '"plan": "basic"' in api.get("/claim", user="bob").text
    signed_out = api.get("/claim", user=None)
    assert 'window.FORM_VARIABLES = {"user": {"name": "Alice Martin", "plan": "premium"}};' in signed_out.text
    assert demo_user_cookie(signed_out).startswith("demo_user=alice;")


def test_the_switch_appears_only_where_the_user_changes_the_result(api: Api) -> None:
    for slug, labels in (
        ("load-definition-variables-data", ["Alice (premium)", "Bob (basic)"]),
        ("resume-progress", ["Alice", "Bob"]),
        ("creator-load-save", ["Alice (can save schemas)", "Bob (cannot save schemas)"]),
    ):
        html = api.get(f"/examples/{slug}").text
        assert 'id="demo-user"' in html, slug
        for label in labels:
            assert f">{label}</option>" in html, f"{slug}: {label}"
    for slug in ("save-response", "store-files", "dashboard", "variable-presets", "fill-together"):
        assert 'id="demo-user"' not in api.get(f"/examples/{slug}").text, slug


def test_bob_and_signed_out_saves_answer_403(api: Api) -> None:
    message = "You don't have editor rights: only editors can change forms"
    for user in ("bob", None, "none", "mallory"):
        for path in ("/api/forms/support", "/api/variable-presets/support"):
            r = api.put(path, json=[], user=user)
            assert (r.status_code, r.json()) == (403, {"error": message}), f"{path} as {user}"


def test_progress_is_per_user_and_answers_401_signed_out(api: Api) -> None:
    for method, message in (("GET", "Sign in to load progress"), ("PUT", "Sign in to save progress"),
                            ("DELETE", "Sign in to clear progress")):
        r = api.request(method, "/api/progress/onboarding", user=None, **({"json": {}} if method == "PUT" else {}))
        assert (r.status_code, r.json()) == (401, {"error": message})
    api.put("/api/progress/demo-users", json={"data": {"who": "alice"}})
    assert api.get("/api/progress/demo-users", user="bob").text == "null"
    assert api.count("progress", "key = '1:demo-users'") == 1
    assert api.get("/api/progress/onboarding", user="mallory").status_code == 401

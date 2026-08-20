"""Settings must be real: stored, consumed, and applied without a restart.

Configuration used to live in .env, resolved into module constants at import
time and copied again onto objects. Nothing written at runtime could reach it.
These tests assert the property that replaced it — a change made through the UI
takes effect in the running process.
"""

import pytest

# ── Live rescheduling ─────────────────────────────────────────

def test_changing_the_hour_reschedules_the_running_job(app, server):
    """Previously this meant editing .env and restarting."""
    before = app.api_get("/system")["scheduler"]
    original = before["hour"]
    new_hour = (original + 5) % 24

    app.request.put(server + "/api/settings",
                    data={"schedule_hour": new_hour})
    after = app.api_get("/system")["scheduler"]

    assert after["hour"] == new_hour
    assert after["next_run"]["display"] != before["next_run"]["display"], \
        "the live cron job should have been rebuilt, not just the stored value"

    app.request.put(server + "/api/settings",
                    data={"schedule_hour": original})


def test_changing_the_timezone_moves_the_next_run(app, server):
    """The timezone was hardcoded in config/settings.py, so this was impossible
    without a code change."""
    original = app.api_get("/system")["scheduler"]["timezone"]

    app.request.put(server + "/api/settings", data={"timezone": "Europe/London"})
    after = app.api_get("/system")["scheduler"]
    assert after["timezone"] == "Europe/London"
    assert any(z in after["next_run"]["display"] for z in ("BST", "GMT")), \
        f"next run should be reported in the new zone: {after['next_run']['display']}"

    app.request.put(server + "/api/settings", data={"timezone": original})
    assert app.api_get("/system")["scheduler"]["timezone"] == original


def test_turning_the_schedule_off_removes_the_job(app, server):
    app.request.put(server + "/api/settings", data={"schedule_enabled": False})
    s = app.api_get("/system")
    assert not s["scheduler"]["enabled"]
    assert not s["scheduler"]["next_run"], "a disabled schedule must not report a next run"
    assert any("automatic" in w.lower() for w in s["warnings"]), \
        "the UI must say that nothing will run on its own"

    app.request.put(server + "/api/settings", data={"schedule_enabled": True})
    assert app.api_get("/system")["scheduler"]["next_run"]


# ── Secrets ───────────────────────────────────────────────────

def test_a_secret_is_never_returned_to_the_browser(app, server):
    secret = "super-secret-value-1234"
    app.request.put(server + "/api/settings", data={"rapidapi_key": secret})

    for path in ("/api/settings", "/api/system", "/api/email/status", "/api/jsearch/status"):
        body = app.request.get(server + path).text()
        assert secret not in body, f"{path} leaked the secret"

    settings = app.request.get(server + "/api/settings").json()
    field = next(f for g in settings["groups"] for f in g["fields"] if f["key"] == "rapidapi_key")
    assert field["configured"] is True
    assert field["value"].startswith("•") and field["value"].endswith("1234"), \
        "the UI should get a masked hint, not the value"

    app.request.put(server + "/api/settings", data={"rapidapi_key": ""})


def test_a_secret_is_encrypted_at_rest(app, server):
    """The database is the artefact most likely to be copied or synced."""
    from core.database import get_connection

    app.request.put(server + "/api/settings", data={"sender_password": "hunter2-app-password"})
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'setting:sender_password'"
        ).fetchone()
    finally:
        conn.close()

    assert row, "the setting should have been stored"
    assert "hunter2" not in row["value"], "the password is sitting in the database in clear"
    assert row["value"].startswith("enc:"), "stored secrets should be tagged as encrypted"

    app.request.put(server + "/api/settings", data={"sender_password": ""})


def test_resending_the_mask_does_not_wipe_the_secret(app, server):
    """The UI only ever holds the mask, so it will send the mask back on save."""
    app.request.put(server + "/api/settings", data={"rapidapi_key": "keep-me-please"})
    app.request.put(server + "/api/settings", data={"rapidapi_key": "••••ease"})
    assert app.api_get("/system")["jsearch"]["configured"], "the stored key was clobbered"
    app.request.put(server + "/api/settings", data={"rapidapi_key": ""})


# ── Values actually reach the code that uses them ─────────────

def test_a_saved_key_reaches_the_source_without_a_restart(app, server):
    """sources/jsearch.py used to copy the key onto the instance at construction."""
    from core import settings_store

    app.request.put(server + "/api/settings", data={"rapidapi_key": "runtime-key"})
    assert settings_store.get("rapidapi_key") == "runtime-key"
    assert app.api_get("/system")["jsearch"]["configured"]

    app.request.put(server + "/api/settings", data={"rapidapi_key": ""})
    assert not app.api_get("/system")["jsearch"]["configured"], \
        "clearing the key must be visible to the running process"


def test_retention_setting_is_the_one_the_collector_uses(app, server):
    from core import settings_store

    app.request.put(server + "/api/settings", data={"stale_job_days": 21})
    assert settings_store.get("stale_job_days") == 21
    app.request.put(server + "/api/settings", data={"stale_job_days": 14})


def test_the_quota_ceiling_is_configurable(app, server):
    """It was hardcoded at 200, so the gauge would have lied on any other plan."""
    app.request.put(server + "/api/settings", data={"jsearch_limit": 10000})
    assert app.api_get("/system")["jsearch"]["limit"] == 10000
    app.request.put(server + "/api/settings", data={"jsearch_limit": 200})


def test_renaming_the_product_updates_the_running_ui(app, server):
    app.request.put(server + "/api/settings", data={"product_name": "Beacon"})
    page = app.goto_app("/")
    page.wait_for_timeout(1500)
    assert page.locator(".brand-name").inner_text().strip() == "Beacon"
    assert "Beacon" in page.title()

    app.request.put(server + "/api/settings", data={"product_name": "Signal"})


# ── Validation ────────────────────────────────────────────────

def test_out_of_range_values_are_clamped_not_stored(app, server):
    r = app.request.put(server + "/api/settings",
                        data={"schedule_hour": 99, "crawl_concurrency": 500}).json()
    fields = {f["key"]: f["value"] for g in r["settings"]["groups"] for f in g["fields"]}
    assert fields["schedule_hour"] == 23
    assert fields["crawl_concurrency"] == 20
    app.request.put(server + "/api/settings",
                    data={"schedule_hour": 9, "crawl_concurrency": 5})


def test_unknown_settings_are_rejected(app, server):
    r = app.request.put(server + "/api/settings", data={"definitely_not_a_setting": "x"})
    assert r.status == 400


# ── Through the UI ────────────────────────────────────────────

def test_settings_page_builds_itself_from_the_schema(app):
    """Adding a setting in Python should surface in the UI with no markup change."""
    page = app.goto_app("/settings")
    page.click("[data-sec='schedule']")
    page.wait_for_selector("[data-sec-body='schedule'] [data-setting]", timeout=10000)

    keys = page.locator("[data-sec-body='schedule'] [data-setting]").evaluate_all(
        "els => els.map(e => e.dataset.setting)")
    assert {"schedule_hour", "timezone", "digest_size"} <= set(keys)


def test_editing_a_setting_in_the_ui_applies_it(app):
    page = app.goto_app("/settings")
    page.click("[data-sec='schedule']")
    page.wait_for_selector("[data-setting='schedule_hour']", timeout=10000)

    before = page.api_get("/system")["scheduler"]["next_run"]["display"]
    page.fill("[data-setting='schedule_hour']", "6")
    page.locator("[data-setting='schedule_hour']").blur()
    page.wait_for_timeout(1800)

    after = page.api_get("/system")["scheduler"]
    assert after["hour"] == 6
    assert after["next_run"]["display"] != before

    page.fill("[data-setting='schedule_hour']", "9")
    page.locator("[data-setting='schedule_hour']").blur()
    page.wait_for_timeout(1200)


def test_secret_fields_are_masked_in_the_page(app, server):
    app.request.put(server + "/api/settings", data={"sender_password": "abcdefghijklmnop"})
    page = app.goto_app("/settings")
    page.click("[data-sec='email']")
    page.wait_for_selector("[data-setting='sender_password']", timeout=10000)

    shown = page.input_value("[data-setting='sender_password']")
    assert "abcdefghijklmnop" not in shown
    assert shown.startswith("•")
    assert page.get_attribute("[data-setting='sender_password']", "type") == "password"

    app.request.put(server + "/api/settings", data={"sender_password": ""})

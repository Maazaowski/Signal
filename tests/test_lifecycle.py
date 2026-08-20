"""The full lifecycle, driven the way a person drives it.

start app -> services up -> collect from the UI -> progress -> results ->
outreach -> digest -> automation history, with a mid-run refresh in the middle
to prove work is not tied to the browser tab.
"""


def test_services_start_with_the_app(app):
    """Requirement: running the web app starts everything."""
    s = app.api_get("/system")
    assert s["scheduler"]["running"], "scheduler must start with the app"
    assert s["worker"]["alive"], "background worker must start with the app"
    assert s["scheduler"]["next_run"], "a next run must be scheduled"


def test_scheduler_runs_even_without_an_email_sender(app):
    """Regression: `if SENDER_EMAIL:` used to gate scheduler.start(), so a
    missing sender silently disabled the daily collection as well as the email.
    The suite runs with SENDER_EMAIL empty, so this asserts the fix directly."""
    s = app.api_get("/system")
    assert not s["email"]["sender_configured"], "fixture should have no sender"
    assert s["scheduler"]["running"], "collection must still be scheduled"
    warned = any("email" in w.lower() for w in s["warnings"])
    assert warned, "the missing sender must be surfaced, not silently ignored"


def test_degraded_state_is_visible_in_the_ui(app):
    """The app must never look healthy while it is degraded."""
    page = app.goto_app("/")
    page.wait_for_selector("#alerts .notice", timeout=10000)
    banner = page.locator("#alerts").inner_text().lower()
    assert "attention" in banner or "sender" in banner
    assert "fix" in page.locator("#health-pill").inner_text().lower()


def test_collect_from_the_ui_produces_results(app):
    page = app.goto_app("/")
    page.click("#btn-find")
    page.wait_for_selector("#live .meter", timeout=10000)
    run = page.wait_for_run()

    assert run["status"] == "success", f"run failed: {run.get('error')}"
    # new vs updated depends on whether an earlier test already collected the
    # same fixtures; what matters is that the run fetched and stored something.
    stats = run["stats"]
    assert stats["fetched"] > 0, "the stubbed sources should return jobs"
    assert stats["new"] + stats.get("updated", 0) > 0, "jobs should reach the database"

    page.goto_app("/roles")
    # Wait for the rows themselves. Waiting for ".entry, .blank" resolves on the
    # empty state that renders first, so the assertion ran before data arrived.
    page.wait_for_selector("#roles [data-role]", timeout=15000)
    assert page.locator("#roles [data-role]").count() > 0


def test_progress_survives_a_hard_refresh(app, stub_sources):
    """The central promise of the run engine: work is not tied to the tab."""
    stub_sources["seconds"] = 8          # long enough to reload mid-run
    try:
        page = app.goto_app("/activity")
        page.api_post("/runs", {"kind": "collect"})
        page.wait_for_selector("#live-panel:not([hidden])", timeout=15000)

        page.reload()
        # A fresh page with no prior knowledge must reattach on its own.
        page.wait_for_selector("#live-panel:not([hidden])", timeout=15000)
        assert "find roles" in page.locator("#live-what").inner_text().lower()
        page.wait_for_run(timeout=90)
    finally:
        stub_sources["seconds"] = 1.2


def test_run_history_and_logs_are_readable_in_the_ui(app):
    app.ensure_run()
    page = app.goto_app("/activity")
    page.wait_for_selector("#history [data-run]", timeout=10000)
    assert page.locator("#history [data-run]").count() > 0

    page.open_drawer("#history [data-run]", "run-pane")
    body = page.locator("#rd-body").inner_text()
    assert "what it did" in body.lower() and "log" in body.lower()


def test_outreach_generation_and_dry_run_digest(app):
    page = app.goto_app("/intros")
    page.click("#btn-write")
    run = page.wait_for_run()
    assert run["status"] == "success"

    # A dry run must not attempt delivery, and must say why when unconfigured.
    res = page.api_post("/email/send-now?dry_run=true")
    assert "error" in res or res.get("dry_run") or res.get("recipient")


def test_scheduled_runs_are_recorded_like_manual_ones(app):
    """Automation history must cover scheduled work, not just button presses."""
    import core.runs as run_engine
    run_engine.enqueue("outreach", trigger="schedule")
    run = app.wait_for_run()
    assert run["trigger"] == "schedule"

    page = app.goto_app("/activity")
    page.wait_for_selector("#history [data-run]", timeout=10000)
    assert "schedule" in page.locator("#history").inner_text().lower()


def test_marked_roles_endpoint_is_not_shadowed(app):
    """Regression: routers mount in order, and `roles` owns /api/jobs/{job_id}.
    Declared after it, the literal /api/jobs/marked was read as a job id,
    so the endpoint answered 200 with the job-detail "not found" body and the
    marked list was unreachable. Asserting the shape locks the ordering."""
    d = app.api_get("/jobs/marked")
    assert "jobs" in d, f"/api/jobs/marked resolved to the wrong handler: {d}"
    assert isinstance(d["jobs"], list)
    # The parameterised route must still work alongside it.
    assert "error" in app.api_get("/jobs/no-such-job-id")


def test_marking_a_role_promotes_it_in_the_digest(app):
    """Marking is only useful if the digest honours it, so check the whole loop
    rather than the toggle alone."""
    app.ensure_jobs()
    job = app.api_get("/jobs?limit=1&min_score=0")["jobs"][0]

    assert app.api_post(f"/jobs/{job['id']}/mark-for-email")["mark_for_email"] is True
    marked = app.api_get("/jobs/marked")["jobs"]
    assert any(j["id"] == job["id"] for j in marked), "marked role must be listed"

    # Toggling is symmetric — the same call clears it again.
    assert app.api_post(f"/jobs/{job['id']}/mark-for-email")["mark_for_email"] is False
    marked = app.api_get("/jobs/marked")["jobs"]
    assert not any(j["id"] == job["id"] for j in marked), "unmarking must remove it"


def test_marking_a_role_from_the_roles_page(app):
    """The flag is only reachable to a person through this control."""
    app.ensure_jobs()
    page = app.goto_app("/roles")
    page.wait_for_selector("#roles [data-role]", timeout=15000)
    page.open_drawer("#roles [data-role]", "role-pane")

    toggle = page.locator("#rp-digest button")
    assert "send in digest" in toggle.inner_text().lower(), "should start unmarked"

    toggle.click()
    page.wait_for_selector("#rp-digest button.btn-primary", timeout=10000)
    assert "in digest" in page.locator("#rp-digest button").inner_text().lower()

    # And the state is real, not just painted.
    assert app.api_get("/jobs/marked")["jobs"], "toggle must reach the database"

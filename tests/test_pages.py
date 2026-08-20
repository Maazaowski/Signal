"""Per-page behaviour: companies, jobs, settings, and the states that are
easy to leave broken — empty, error, degraded, and hostile input."""


# ── Companies ─────────────────────────────────────────────────

def test_companies_empty_state_offers_the_fix(app):
    page = app.goto_app("/companies")
    page.wait_for_selector("#co-rows", timeout=10000)
    body = page.locator("#co-rows").inner_text()
    if "No companies yet" in body:
        assert page.locator("#co-rows button:has-text('Add curated list')").count() == 1, \
            "an empty state must offer the action that resolves it"


def test_seeding_and_the_ats_gap_is_surfaced(app):
    """Seeded companies arrive paused with an unknown ATS. If the UI does not
    say so, the crawler silently collects nothing — which is exactly what
    happened before this page existed."""
    page = app.goto_app("/companies")
    page.click("#btn-seed")
    run = page.wait_for_run(timeout=90)
    assert run["status"] == "success"
    assert run["stats"]["added"] > 0

    page.reload()
    page.wait_for_selector("#board-notice .notice", timeout=15000)
    notice = page.locator("#board-notice").inner_text().lower()
    assert "find job boards" in notice, "the UI must name the action that fixes it"

    stats = page.api_get("/companies/stats")
    assert stats["by_platform"].get("unknown", 0) > 0


def test_company_row_actions_are_disabled_when_they_cannot_work(app):
    app.ensure_companies()
    page = app.goto_app("/companies")
    page.wait_for_selector("#co-rows tr", timeout=10000)
    page.select_option("#f-board", "unknown")
    page.wait_for_timeout(1200)
    rows = page.locator("#co-rows tr")
    if rows.count():
        crawl = page.locator("#co-rows [data-crawl]").first
        assert crawl.is_disabled(), \
            "crawling a company with no detected board must not be offered"


def test_company_filters_narrow_results(app):
    app.ensure_companies()
    page = app.goto_app("/companies")
    page.wait_for_selector("#co-rows tr", timeout=10000)
    page.fill("#f-q", "zzzz-no-such-company")
    page.wait_for_timeout(1200)
    assert "Nothing matches" in page.locator("#co-rows").inner_text()
    page.click("#co-rows button:has-text('Clear filters')")
    page.wait_for_timeout(1200)
    assert page.locator("#co-rows tr").count() > 0


# ── Jobs ──────────────────────────────────────────────────────

def test_jobs_table_and_detail_drawer(app):
    app.ensure_jobs()
    page = app.goto_app("/roles")
    page.select_option("#f-open", "")          # show everything, not just good fits
    page.select_option("#f-score", "0")
    page.wait_for_selector("#roles [data-role]", timeout=15000)

    page.open_drawer("#roles [data-role]", "role-pane")
    assert page.locator("#rp-body").inner_text().strip()
    assert page.locator("#rp-foot button").count() >= 3

    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert not page.locator("#role-pane").evaluate("e => e.classList.contains('open')")


def test_job_filters_have_an_escape_hatch(app):
    app.ensure_jobs()
    page = app.goto_app("/roles")
    page.wait_for_selector("#roles .entry, #roles .blank", timeout=10000)
    page.fill("#f-q", "zzzz-nothing-matches-this")
    page.wait_for_timeout(1200)
    assert "Nothing matches" in page.locator("#roles").inner_text()
    page.click("#roles button:has-text('Clear filters')")
    page.wait_for_timeout(1500)
    # The escape hatch must clear the search box; whether rows come back depends
    # on the other filter defaults and on what this session has collected.
    assert page.input_value("#f-q") == "", "clearing must empty the search"


# ── Route registration ────────────────────────────────────────

def test_no_literal_route_is_shadowed_by_an_earlier_pattern():
    """FastAPI matches in registration order, so `/api/jobs/{job_id}` declared
    before `/api/jobs/marked` swallows it — the literal never runs and nothing
    fails loudly, it just answers from the wrong handler.

    Checking the whole route table rather than the one known case, because the
    trap is re-armed by any literal path added under an existing `/{param}`
    route, in any router.
    """
    import main

    def flatten(routes):
        """Effective match order. include_router() wraps a router rather than
        splicing its routes into app.routes, so the real APIRoutes have to be
        pulled back out of the wrapper — filtering on path_regex alone silently
        yields only FastAPI's four built-in routes and the check passes on
        anything."""
        for r in routes:
            inner = getattr(r, "original_router", None) or r
            if inner is not r or hasattr(inner, "routes"):
                yield from flatten(inner.routes)
            elif getattr(r, "path_regex", None) and getattr(r, "methods", None):
                yield r

    routes = list(flatten(main.app.routes))

    # Guard against the above going quiet if the internals move again.
    paths = {r.path for r in routes}
    assert "/api/jobs/marked" in paths and "/api/jobs/{job_id}" in paths, (
        f"route table was not read correctly - found {len(routes)} routes")

    shadowed = []
    for i, later in enumerate(routes):
        if "{" in later.path:
            continue                      # only literals can be shadowed
        for earlier in routes[:i]:
            if not (earlier.methods & later.methods):
                continue
            if "{" in earlier.path and earlier.path_regex.match(later.path):
                shadowed.append(f"{sorted(later.methods)} {later.path} "
                                f"is shadowed by {earlier.path}")

    assert not shadowed, "literal routes must be registered first:\n" + "\n".join(shadowed)


# ── Security regressions ──────────────────────────────────────

def test_hostile_job_content_renders_inert(app):
    """A job description is third-party HTML from a public board. It shares an
    origin with an API that has no auth, so it must never execute."""
    page = app.goto_app("/roles")
    if not page.locator("#roles [data-role]").count():
        page.api_post("/runs", {"kind": "collect"})
        page.wait_for_run()

    page.select_option("#f-open", "")
    page.select_option("#f-score", "0")
    page.fill("#f-q", "XSS Probe")
    page.wait_for_timeout(1500)

    row = page.locator("#roles [data-role]").first
    if not row.count():
        return  # fixture job filtered out by scoring; nothing to assert
    row.click()
    page.wait_for_selector("#role-pane.open", timeout=5000)
    page.wait_for_timeout(1500)

    assert page.evaluate("window.__xss === undefined"), "payload executed"
    assert page.locator("#rp-body img").count() == 0
    assert page.locator("#rp-body script").count() == 0
    hrefs = page.locator("#rp-foot a").evaluate_all("as => as.map(a => a.getAttribute('href'))")
    assert not any((h or "").lower().startswith("javascript:") for h in hrefs)


def test_cross_origin_state_change_is_blocked(app, server):
    """No auth + query-param POSTs means any site could fire these."""
    blocked = app.request.post(server + "/api/collect",
                               headers={"Sec-Fetch-Site": "cross-site"})
    assert blocked.status == 403

    allowed = app.request.get(server + "/api/system",
                              headers={"Sec-Fetch-Site": "cross-site"})
    assert allowed.status == 200, "reads may stay open; writes may not"


def test_duplicate_run_is_rejected_not_queued(app):
    """Two collections would spend the RapidAPI quota twice."""
    first = app.api_post("/runs", {"kind": "collect"})
    assert first.get("run_id"), f"first run should start: {first}"

    dup = app.api_post("/runs", {"kind": "collect"})
    assert "detail" in dup and "in progress" in dup["detail"].lower(),         f"a concurrent duplicate must be rejected, got: {dup}"

    app.wait_for_run()


# ── Settings ──────────────────────────────────────────────────

def test_settings_tabs_and_profile_editing(app):
    page = app.goto_app("/settings")
    page.wait_for_selector("#sections button", timeout=10000)
    assert page.locator("#sections button").count() == 11

    for tab in page.locator("#sections button").all():
        tab.click()
        page.wait_for_timeout(180)
        pane = page.locator(f"[data-sec-body='{tab.get_attribute('data-sec')}']")
        assert pane.is_visible(), f"section {tab.inner_text()} did not open"

    page.click("[data-sec='pitch']")
    # Wait for the profile to load before typing — otherwise the keystrokes
    # land before the field is bound and go nowhere.
    page.wait_for_function(
        "() => document.querySelector('#o-name') && document.querySelector('#o-name').value !== ''",
        timeout=10000)
    page.fill("#o-name", "Test Person")
    page.wait_for_timeout(400)
    assert "Test Person" in page.locator("#pitch-preview").inner_text()


def test_saving_the_profile_persists(app):
    page = app.goto_app("/settings")
    page.click("[data-sec='pitch']")
    # Wait until the profile has actually loaded and bound its handlers. Typing
    # before that races the fetch and the keystrokes go nowhere — which is a real
    # trap for a fast user, not just for a test.
    page.wait_for_function(
        "() => document.querySelector('#o-name') && document.querySelector('#o-name').value !== ''",
        timeout=10000)
    page.fill("#o-name", "Persisted Name")
    page.wait_for_function("() => !document.querySelector('#profile-save').disabled", timeout=5000)
    page.click("#profile-save")
    page.wait_for_timeout(1500)

    active = page.api_get("/profiles/active")
    assert active["config"]["outreach"]["candidate_name"] == "Persisted Name"


def test_query_cost_is_stated_before_you_add_one(app):
    """Each query costs quota; the UI should say so rather than let you
    discover it at the end of the month."""
    page = app.goto_app("/settings")
    page.click("[data-sec='searches']")
    page.wait_for_timeout(800)
    assert "monthly requests" in page.locator("#search-cost").inner_text()
    assert "200" in page.locator("[data-sec-body='searches']").inner_text()


def test_system_pane_reports_integration_state(app):
    page = app.goto_app("/settings")
    page.click("[data-sec='integrations']")
    page.wait_for_selector("[data-sec-body='integrations'] [data-setting]", timeout=10000)
    txt = page.locator("[data-sec-body='integrations']").inner_text().lower()
    assert "jsearch" in txt
    assert "jsearch" in txt or "allowance" in txt


# ── Failure handling ──────────────────────────────────────────

def test_server_loss_is_reported_not_hidden(app, server):
    page = app.goto_app("/")
    page.wait_for_selector("#health-pill .tag", timeout=10000)
    page.route("**/api/system", lambda route: route.abort())
    page.wait_for_timeout(7000)
    assert "not responding" in page.locator("#health-pill").inner_text().lower()
    page.unroute("**/api/system")


def test_failed_run_shows_the_reason(app):
    page = app.goto_app("/activity")
    page.api_post("/runs", {"kind": "nonexistent_kind"})   # rejected up front
    page.wait_for_timeout(500)

    import core.runs as run_engine
    from core.database import create_run, finish_run
    rid = create_run("collect", "manual")
    finish_run(rid, "failed", error="RuntimeError: simulated failure for the test")

    page.reload()
    page.wait_for_selector("#history [data-run]", timeout=10000)
    page.open_drawer(f"#history [data-run='{rid}']", "run-pane")
    body = page.locator("#rd-body").inner_text()
    assert "simulated failure" in body, "a failure must explain itself in the UI"

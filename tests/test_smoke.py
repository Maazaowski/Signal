"""Every page renders, navigates, and reports its state honestly."""

import pytest

PAGES = [
    ("/",           "Today"),
    ("/roles",      "Roles"),
    ("/intros",     "Intros"),
    ("/companies",  "Companies"),
    ("/activity",   "Activity"),
    ("/settings",   "Settings"),
]


@pytest.mark.parametrize("path,heading", PAGES)
def test_page_renders(app, path, heading):
    page = app.goto_app(path)
    assert page.locator(".bar h1").inner_text().strip() == heading
    assert page.locator(".nav-item").count() == 6
    assert page.locator(".rail").is_visible()


@pytest.mark.parametrize("path,heading", PAGES)
def test_no_console_errors(app, path, heading):
    errors = []
    app.on("pageerror", lambda e: errors.append(str(e)))
    app.goto_app(path)
    app.wait_for_timeout(2500)
    assert not errors, f"{path} raised: {errors}"


@pytest.mark.parametrize("path,heading", PAGES)
def test_icons_are_drawn_not_typed(app, path, heading):
    """The interface used to navigate with Unicode glyphs, which never aligned
    to the baseline and rendered differently on every machine. Every icon is now
    a drawn SVG from the sprite."""
    page = app.goto_app(path)
    page.wait_for_timeout(1200)
    assert page.locator("svg use").count() >= 6, "icons should come from the sprite"
    body = page.locator("body").inner_text()
    stray = [g for g in "◎▤✉⌂⟳⚙⚠ℹ○×" if g in body]
    assert not stray, f"{path} still renders glyph icons: {stray}"


def test_navigation_between_pages(app):
    page = app.goto_app("/")
    page.click(".nav-item:has-text('Companies')")
    page.wait_for_url("**/companies")
    assert page.locator(".bar h1").inner_text().strip() == "Companies"

    page.click(".nav-item:has-text('Activity')")
    page.wait_for_url("**/activity")
    assert page.locator(".bar h1").inner_text().strip() == "Activity"


def test_active_nav_item_matches_page(app):
    for path, heading in PAGES:
        page = app.goto_app(path)
        active = page.locator(".nav-item.active")
        assert active.count() == 1
        assert heading.lower() in active.inner_text().strip().lower()


@pytest.mark.parametrize("old,new", [
    ("/jobs", "/roles"),
    ("/dashboard", "/roles"),
    ("/outreach", "/intros"),
    ("/automation", "/activity"),
    ("/profile", "/settings"),
])
def test_old_urls_still_work(app, server, old, new):
    """Pages were renamed; bookmarks and older docs must not break."""
    app.goto(server + old)
    assert app.url.endswith(new), f"{old} should land on {new}"


def test_health_reaches_the_sidebar(app):
    page = app.goto_app("/")
    page.wait_for_selector("#health-pill .tag", timeout=10000)
    txt = page.locator("#health-pill").inner_text()
    assert txt.strip() and "Checking" not in txt


def test_theme_choice_survives_a_reload(app):
    page = app.goto_app("/")
    page.click("#theme-btn")
    chosen = page.evaluate("document.documentElement.getAttribute('data-theme')")
    page.reload()
    page.wait_for_timeout(400)
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == chosen


def test_dark_theme_paints_its_own_background(app):
    """A transparent body would borrow whatever is behind it."""
    page = app.goto_app("/")
    page.evaluate("theme.apply('dark')")
    page.wait_for_timeout(250)
    bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
    assert bg not in ("rgba(0, 0, 0, 0)", "transparent")


def test_product_name_is_used_throughout(app):
    page = app.goto_app("/")
    page.wait_for_timeout(1500)
    name = page.api_get("/system")["product_name"]
    assert page.locator(".brand-name").inner_text().strip() == name
    assert name in page.title()


def test_assets_are_cache_busted_by_content(app):
    """The buster used to be a hand-maintained constant, so any stylesheet edit
    shipped behind a stale cached copy until someone remembered to bump it."""
    from api.deps import asset_stamp
    stamp = asset_stamp()

    page = app.goto_app("/")
    hrefs = page.locator("link[rel=stylesheet]").evaluate_all(
        "ls => ls.map(l => l.getAttribute('href'))")
    assert hrefs, "the page should link stylesheets"
    assert all(f"v={stamp}" in h for h in hrefs),         f"stylesheets should carry the content stamp {stamp}: {hrefs}"


def test_health_stays_visible_on_a_narrow_screen(app):
    """Health is most important where there is least room for the banner."""
    page = app.goto_app("/")
    page.set_viewport_size({"width": 760, "height": 1024})
    page.wait_for_timeout(900)
    assert page.locator("#health-pill").is_visible(), "health was hidden on tablet"
    assert page.locator("#theme-btn").is_visible(), "theme control was hidden on tablet"
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 2"),         "the page scrolls sideways on tablet"
    page.set_viewport_size({"width": 1440, "height": 900})

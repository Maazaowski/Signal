"""Test fixtures.

Two things matter here:

1. The suite must never touch the real jobs.db. Every session gets a throwaway
   database via the JOBS_DB_PATH override in config/settings.py.

2. The suite must never call JSearch. Each request costs one of the 200 free
   RapidAPI calls per month, so a test run could burn a meaningful chunk of the
   user's monthly quota. RAPIDAPI_KEY is forced empty and the outbound HTTP
   sources are replaced with local fakes, which also makes runs fast and
   deterministic.
"""

import os
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest

# Must be set before anything imports config.settings.
_TMP = Path(tempfile.mkdtemp(prefix="jobhunter-tests-"))
os.environ["JOBS_DB_PATH"] = str(_TMP / "test.db")
os.environ["RAPIDAPI_KEY"] = ""          # never spend real quota
os.environ["SENDER_EMAIL"] = ""          # never send real mail
os.environ["SENDER_APP_PASSWORD"] = ""
os.environ["RECIPIENT_EMAIL"] = "test@example.com"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def fake_jobs():
    """Deterministic job fixtures covering every location-fit branch."""
    from core.models import Job
    return [
        Job(title="Senior Python Backend Engineer", company="Acme",
            location="Karachi, Pakistan", description="6+ years Django REST Postgres Redis",
            url="https://example.com/1", source="remotive"),
        Job(title="Staff Backend Engineer (Python)", company="Globex",
            location="Remote - Worldwide", description="Python FastAPI microservices at scale",
            url="https://example.com/2", source="remotive"),
        Job(title="Senior Backend Engineer", company="Initech",
            location="London", description="We are a global company. Python and Django.",
            url="https://example.com/3", source="remoteok"),
        Job(title="Backend Engineer", company="Umbrella",
            location="Remote (US only)", description="Must reside in the US. Python.",
            url="https://example.com/4", source="remoteok"),
        Job(title="Junior Python Developer", company="Hooli",
            location="Lahore, Pakistan", description="Fresher, 0-1 years, entry level",
            url="https://example.com/5", source="arbeitnow"),
        # Hostile input: must render inert in the UI, not execute.
        Job(title="XSS Probe Engineer", company="EvilCorp",
            location="Remote - Worldwide",
            description='<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>Python Django',
            url="javascript:window.__xss=3", source="remotive"),
    ]


@pytest.fixture(scope="session", autouse=True)
def stub_sources(fake_jobs):
    """Replace every outbound source with a local fake.

    Without this the suite would hit the real Remotive/RemoteOK/Arbeitnow APIs
    and ~200 company career pages on every run.
    """
    import asyncio

    import core.bulk_discover as bulk
    from sources import arbeitnow, remoteok, remotive

    # A small delay keeps runs observable. A real collection takes 1-2 minutes;
    # an instantaneous stub would finish before any test could assert on
    # progress, and would not exercise the polling paths at all.
    # Mutable so a test needing a longer window (e.g. refresh-mid-run) can
    # raise it without slowing the whole suite down.
    delay = {"seconds": 1.2}

    def _maker(source_name):
        async def _fetch(self):
            await asyncio.sleep(delay["seconds"])
            return [j for j in fake_jobs if j.source == source_name]
        return _fetch

    remotive.RemotiveSource.fetch = _maker("remotive")
    remoteok.RemoteOKSource.fetch = _maker("remoteok")
    arbeitnow.ArbeitnowSource.fetch = _maker("arbeitnow")

    # ATS detection probes Greenhouse/Lever/Ashby over the network. Without
    # this stub the suite would make hundreds of real outbound requests.
    async def _fake_detect(companies, concurrency=10):
        await asyncio.sleep(0.3)
        for i, c in enumerate(companies):
            if i % 3 == 0:                       # a third resolve, like reality
                c["ats_platform"] = "greenhouse"
                c["ats_slug"] = (c.get("domain") or c["name"]).split(".")[0].lower()
            else:
                c["ats_platform"] = "unknown"
                c["ats_slug"] = ""
        return companies

    bulk.batch_detect_ats = _fake_detect
    import core.ats_detect as ats_detect
    ats_detect.batch_detect_ats = _fake_detect
    yield delay


@pytest.fixture(scope="session")
def server(stub_sources):
    """Run the real app in a background thread on a free port."""
    import uvicorn

    import main

    port = _free_port()
    config = uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    for _ in range(100):                       # wait for startup to complete
        if srv.started:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("Server did not start")

    yield base

    srv.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(autouse=True)
def clean_state(server):
    """Reset volatile state before every test.

    The suite shares one server and one database for speed. Without this, each
    test inherits whatever the previous one collected, filtered or left running,
    which made failures depend on execution order rather than on the code. Tests
    now start empty and use the ensure_* helpers to build exactly what they need.

    Profiles, settings and the schema are preserved — they are configuration,
    not test residue.
    """
    from core import runlog
    from core.database import get_active_run, get_connection

    # Let any in-flight run finish first. Deleting its row would not stop the
    # worker; it would just hide it, and the next test would start a second run
    # alongside it.
    deadline = time.time() + 90
    while get_active_run() and time.time() < deadline:
        time.sleep(0.2)

    conn = get_connection()
    try:
        for table in ("jobs", "outreach", "runs", "run_logs", "api_usage",
                      "email_log", "companies"):
            try:
                conn.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()
    runlog.clear()
    yield


@pytest.fixture()
def app(page, server):
    """A page pointed at the app, with a helper for API calls and run waiting."""
    # These timings were tuned on a fast desktop. CI runners are slower, and a
    # timeout there is a false failure rather than a regression, so give them
    # more room without slowing the local suite.
    page.set_default_timeout(30000 if os.environ.get("CI") else 15000)

    def goto(path="/"):
        page.goto(server + path, wait_until="domcontentloaded")
        return page

    def get(path):
        return page.request.get(server + "/api" + path).json()

    def post(path, data=None):
        return page.request.post(server + "/api" + path, data=data).json()

    def wait_for_run(timeout=60):
        """Block until a run has both started and finished, then return it.

        `clean_state` empties the runs table before every test, so between
        starting a run and its row appearing there is a window with no active
        run and no history. Treating that as "finished" returned None and the
        caller crashed on None["status"] — rare on a fast machine, common on a
        slow one. An empty table means not started yet, so keep waiting.
        """
        if os.environ.get("CI"):
            timeout *= 2
        deadline = time.time() + timeout
        d: dict = {}
        while time.time() < deadline:
            d = get("/runs?limit=1")
            if not d["active"] and d["runs"]:
                return d["runs"][0]
            time.sleep(0.3)
        raise AssertionError(
            f"No run started and finished within {timeout}s "
            f"(active={d.get('active')}, history={len(d.get('runs', []))})")

    page.goto_app = goto
    page.api_get = get
    page.api_post = post
    page.wait_for_run = wait_for_run

    def ensure_jobs():
        """Guarantee the database has jobs, whatever ran before."""
        if get("/jobs?limit=1&min_score=0").get("count", 0) == 0:
            post("/runs", {"kind": "collect"})
            wait_for_run(timeout=90)

    def ensure_run():
        """Guarantee at least one finished run exists in history."""
        if not get("/runs?limit=1").get("runs"):
            post("/runs", {"kind": "outreach"})
            wait_for_run(timeout=90)

    def open_drawer(selector, drawer_id, attempts=3):
        """Click a row and wait for its drawer to populate.

        Retries because these tables re-render on their polling interval, which
        can detach the row between locating it and clicking it. Also waits for
        content rather than just the open class — the body is filled by a fetch
        that lands after the animation.
        """
        last = None
        for _ in range(attempts):
            try:
                page.locator(selector).first.click(timeout=5000)
                page.wait_for_selector(f"#{drawer_id}.open", timeout=5000)
                page.wait_for_function(
                    f"() => document.querySelector('#{drawer_id} .pane-bd')"
                    f"?.innerText.trim().length > 40",
                    timeout=5000,
                )
                return
            except Exception as e:
                last = e
                # An open panel leaves a scrim over the page, which swallows the
                # retry click. Dismiss it before trying again.
                page.keyboard.press("Escape")
                page.wait_for_timeout(600)
        raise AssertionError(f"drawer {drawer_id} never populated: {last}")

    def ensure_companies():
        if get("/companies/stats").get("total", 0) == 0:
            post("/runs", {"kind": "seed", "mega": True})
            wait_for_run(timeout=120)

    page.ensure_jobs = ensure_jobs
    page.ensure_run = ensure_run
    page.ensure_companies = ensure_companies
    page.open_drawer = open_drawer

    # Isolation: only one run executes at a time, so a run left in flight by the
    # previous test would make this one's start request 409 and its assertions
    # fail for unrelated reasons.
    try:
        if get("/runs/active").get("active"):
            wait_for_run(timeout=90)
    except Exception:
        pass

    return page


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 1440, "height": 900}}

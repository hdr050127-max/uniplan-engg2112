import json
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from timetable_scraper import SYDNEY
from uniplan.auto_fetch import AutoFetcher
from uniplan.server import AppServer


PROFILE = {"year": 2026, "session_code": "S2C", "unit_codes": ["CIVL3206"]}


class FakeCatalog:
    def __init__(self, root):
        self.snapshots = []
        self.processed_dir = root / "data/processed"
        self.refreshed = 0

    def refresh(self):
        self.refreshed += 1


class AutoFetchTests(unittest.TestCase):
    def test_recent_snapshot_is_reused_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            catalog = FakeCatalog(root)
            catalog.snapshots = [{
                "year": 2026, "session_code": "S2C", "unit_codes": ["CIVL3206"],
                "snapshot_time": datetime.now(SYDNEY).isoformat(),
            }]
            fetcher = AutoFetcher(root, robots_check=lambda: self.fail("robots check called"),
                                  collector=lambda *args, **kwargs: self.fail("collector called"))
            self.assertEqual(fetcher.ensure(PROFILE, catalog)["status"], "cached")

    def test_missing_cache_stops_before_live_request_when_robots_disallows(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []
            def collect(*args, **kwargs):
                calls.append(kwargs["offline"])
                return [], {"complete": False, "units": {"CIVL3206": {"status": "error"}}}
            fetcher = AutoFetcher(Path(temp), robots_check=lambda: False, collector=collect)
            result = fetcher.ensure(PROFILE, FakeCatalog(Path(temp)))
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(calls, [True])

    def test_explicitly_allowed_live_lookup_writes_snapshot_and_refreshes_catalog(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            calls = []
            def collect(*args, **kwargs):
                calls.append(kwargs["offline"])
                if kwargs["offline"]:
                    return [], {"complete": False, "units": {"CIVL3206": {"status": "error"}}}
                return [{
                    "meeting_id": "one", "unit_code": "CIVL3206", "year": 2026,
                    "session_code": "S2C", "group_id": "CIVL3206|Lecture",
                    "option_id": "CIVL3206|Lecture|01", "date": "2026-08-03",
                    "start_min": 540, "end_min": 600, "status": "available",
                    "snapshot_time": datetime.now(SYDNEY).isoformat(),
                }], {"complete": True, "units": {"CIVL3206": {"status": "ok"}}}
            catalog = FakeCatalog(root)
            fetcher = AutoFetcher(root, allow_robots_disallowed=True,
                                  robots_check=lambda: False, collector=collect)
            result = fetcher.ensure(PROFILE, catalog)
            self.assertEqual(result["status"], "fetched")
            self.assertEqual(calls, [True, False])
            self.assertEqual(catalog.refreshed, 1)
            self.assertEqual(len(list(catalog.processed_dir.glob("*.csv"))), 1)
            report_path = next(catalog.processed_dir.glob("*_report.json"))
            self.assertEqual(json.loads(report_path.read_text())["robots_policy"], "disallowed_override")

    def test_form_submit_triggers_auto_fetch_only_for_valid_input(self):
        with tempfile.TemporaryDirectory() as temp:
            with AppServer(("127.0.0.1", 0), root=Path(temp)) as server:
                calls = []
                class Fetcher:
                    def ensure(self, profile, catalog):
                        calls.append(profile["unit_codes"])
                        return {"status": "blocked", "message": "source blocked"}
                server.fetcher = Fetcher()
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    url = f"http://127.0.0.1:{server.server_address[1]}/api/prepare"
                    payload = {"profile": {"year": 2026, "session_code": "S2C",
                                           "unit_codes": ["civl3206"], "unavailable_windows": []},
                               "save": False}
                    request = Request(url, data=json.dumps(payload).encode(),
                                      headers={"Content-Type": "application/json"})
                    with urlopen(request) as response:
                        result = json.load(response)
                    self.assertEqual(calls, [["CIVL3206"]])
                    self.assertEqual(result["fetch"]["status"], "blocked")
                    self.assertEqual(result["blockers"][0]["code"], "auto_fetch_blocked")
                finally:
                    server.shutdown()
                    worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()

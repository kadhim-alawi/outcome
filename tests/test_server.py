"""The demo server's HTTP surface.

This file exists because `/?pace=5000` returned 404. Routing compared
`self.path` — which includes the query string — against `"/"`, so *any* query
parameter took the whole page down. It was found while timing a rehearsal;
without that it would have been found while recording.

The server runs on an ephemeral port in a thread, so these are real requests
over a real socket rather than handler methods called directly. The routing bug
lived precisely in the gap between those two things.
"""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from outcome import server


class ServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.Handler.live = False
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def get(self, path: str):
        try:
            with urllib.request.urlopen(f"{self.base}{path}", timeout=10) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def post(self, path: str, payload: dict):
        request = urllib.request.Request(
            f"{self.base}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())


class Routing(ServerTestCase):
    def test_the_page_is_served(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"OUTCOME", body)

    def test_a_query_string_does_not_break_the_page(self):
        """The regression. `?pace=` is how the demo is slowed to narration
        speed, and it used to 404 the entire UI."""
        for path in ("/?pace=5000", "/index.html?pace=250", "/?a=1&b=2"):
            with self.subTest(path=path):
                status, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertIn(b"OUTCOME", body)

    def test_api_routes_tolerate_a_query_string(self):
        for path in ("/api/mode", "/api/mode?x=1", "/api/scenarios", "/api/scenarios?x=1"):
            with self.subTest(path=path):
                status, _ = self.get(path)
                self.assertEqual(status, 200)

    def test_unknown_routes_are_404(self):
        for path in ("/nope", "/api/nope", "/api/runs/does-not-exist"):
            with self.subTest(path=path):
                self.assertEqual(self.get(path)[0], 404)

    def test_the_favicon_is_served(self):
        status, body = self.get("/favicon.ico")
        self.assertEqual(status, 200)
        self.assertIn(b"svg", body)


class Scenarios(ServerTestCase):
    def test_the_featured_scenario_comes_first(self):
        _status, body = self.get("/api/scenarios")
        names = [s["name"] for s in json.loads(body)["scenarios"]]
        self.assertEqual(names[0], "supplier-replacement")

    def test_each_carries_a_usable_outcome_definition(self):
        _status, body = self.get("/api/scenarios")
        for scenario in json.loads(body)["scenarios"]:
            with self.subTest(scenario=scenario["name"]):
                self.assertTrue(scenario["outcome"]["goal"])
                self.assertTrue(scenario["outcome"]["organizations"])


class RunningAnOutcome(ServerTestCase):
    def test_a_run_reaches_approval_then_resolves(self):
        status, data = self.post("/api/runs", {"scenario": "supplier-replacement"})
        self.assertEqual(status, 200)
        self.assertEqual(data["outcome"]["status"], "awaiting_approval")

        status, data = self.post(
            "/api/decide", {"run_id": data["outcome"]["id"], "approve": True}
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["outcome"]["status"], "resolved")
        self.assertEqual(data["outcome"]["resolution"]["reference"], "BWD-48291")

    def test_a_scenario_name_cannot_escape_the_scenarios_directory(self):
        status, data = self.post("/api/runs", {"scenario": "../../etc/passwd"})
        self.assertEqual(status, 400)
        self.assertIn("Unknown scenario", data["error"])

    def test_a_bad_phone_number_is_refused_before_anything_runs(self):
        status, data = self.post(
            "/api/runs",
            {
                "scenario": "supplier-replacement",
                "outcome": {
                    "goal": "g",
                    "organizations": [{"name": "A", "phone": "555-0100"}],
                },
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("E.164", data["error"])

    def test_deciding_on_an_unknown_run_is_404(self):
        status, _ = self.post("/api/decide", {"run_id": "out_nope", "approve": True})
        self.assertEqual(status, 404)

    def test_interpret_reads_a_sentence(self):
        status, data = self.post(
            "/api/interpret", {"text": "Replace it before Friday, under $500"}
        )
        self.assertEqual(status, 200)
        kinds = {c["kind"] for c in data["constraints"]}
        self.assertIn("budget", kinds)

    def test_interpret_needs_something_to_read(self):
        self.assertEqual(self.post("/api/interpret", {"text": "  "})[0], 400)


if __name__ == "__main__":
    unittest.main()

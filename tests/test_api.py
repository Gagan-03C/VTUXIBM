"""
QuantumFlow — Test Suite: Flask API
tests/test_api.py  ·  Owner: Frontend Engineer
"""

import json
import pytest
from api.app import app as flask_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


VALID_TRAFFIC_INPUT = {
    "(0,0)": {"ns_count": 3, "ew_count": 1},
    "(0,1)": {"ns_count": 0, "ew_count": 5},
    "(1,0)": {"ns_count": 2, "ew_count": 2},
    "(1,1)": {"ns_count": 1, "ew_count": 0},
}


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data),
                       content_type="application/json")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class TestHealth:
    def test_health_200(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200

    def test_health_has_status_ok(self, client):
        data = r = client.get("/api/health").get_json()
        assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /api/simulate
# ---------------------------------------------------------------------------
class TestSimulate:
    def test_valid_request_200(self, client):
        r = post_json(client, "/api/simulate",
                      {"grid_size": 2, "num_vehicles": 8})
        assert r.status_code == 200

    def test_response_has_traffic_input(self, client):
        r = post_json(client, "/api/simulate",
                      {"grid_size": 2, "num_vehicles": 4})
        data = r.get_json()
        assert "traffic_input" in data
        assert "congestion_map" not in data   # old key must not appear

    def test_response_has_run_id(self, client):
        r = post_json(client, "/api/simulate",
                      {"grid_size": 2, "num_vehicles": 4})
        assert "run_id" in r.get_json()

    def test_missing_grid_size_400(self, client):
        r = post_json(client, "/api/simulate", {"num_vehicles": 5})
        assert r.status_code == 400

    def test_missing_num_vehicles_400(self, client):
        r = post_json(client, "/api/simulate", {"grid_size": 2})
        assert r.status_code == 400

    def test_grid_too_large_400(self, client):
        r = post_json(client, "/api/simulate",
                      {"grid_size": 99, "num_vehicles": 5})
        assert r.status_code == 400

    def test_non_json_400(self, client):
        r = client.post("/api/simulate", data="not json",
                        content_type="text/plain")
        assert r.status_code == 400

    def test_grid_is_square_nxn(self, client):
        r = post_json(client, "/api/simulate",
                      {"grid_size": 3, "num_vehicles": 10})
        data = r.get_json()
        grid = data["grid"]
        assert len(grid) == 3
        for row in grid:
            assert len(row) == 3


# ---------------------------------------------------------------------------
# POST /api/optimize — classical
# ---------------------------------------------------------------------------
class TestOptimizeClassical:
    def test_valid_classical_200(self, client):
        r = post_json(client, "/api/optimize",
                      {"traffic_input": VALID_TRAFFIC_INPUT, "method": "classical"})
        assert r.status_code == 200

    def test_algorithm_is_greedy(self, client):
        r = post_json(client, "/api/optimize",
                      {"traffic_input": VALID_TRAFFIC_INPUT, "method": "classical"})
        assert r.get_json()["algorithm"] == "greedy"

    def test_timing_plan_in_response(self, client):
        r = post_json(client, "/api/optimize",
                      {"traffic_input": VALID_TRAFFIC_INPUT, "method": "classical"})
        data = r.get_json()
        assert "timing_plan" in data
        for iid, timing in data["timing_plan"].items():
            assert "ns_green" in timing
            assert "ew_green" in timing
            assert timing["ns_green"] + timing["ew_green"] == 60

    def test_metrics_in_response(self, client):
        r = post_json(client, "/api/optimize",
                      {"traffic_input": VALID_TRAFFIC_INPUT, "method": "classical"})
        m = r.get_json()["metrics"]
        for field in ("total_vehicles", "vehicles_served", "remaining_queue",
                      "avg_wait_sec", "total_delay_sec", "runtime_ms"):
            assert field in m

    def test_invalid_traffic_input_400(self, client):
        bad = {"(0,0)": {"ns_count": -1, "ew_count": 0},
               "(0,1)": {"ns_count": 0,  "ew_count": 0},
               "(1,0)": {"ns_count": 0,  "ew_count": 0},
               "(1,1)": {"ns_count": 0,  "ew_count": 0}}
        r = post_json(client, "/api/optimize",
                      {"traffic_input": bad, "method": "classical"})
        assert r.status_code == 400

    def test_missing_traffic_input_400(self, client):
        r = post_json(client, "/api/optimize", {"method": "classical"})
        assert r.status_code == 400

    def test_invalid_method_400(self, client):
        r = post_json(client, "/api/optimize",
                      {"traffic_input": VALID_TRAFFIC_INPUT, "method": "magic"})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/compare
# ---------------------------------------------------------------------------
class TestCompare:
    def _get_run_id(self, client, method="classical"):
        r = post_json(client, "/api/optimize",
                      {"traffic_input": VALID_TRAFFIC_INPUT, "method": method})
        return r.get_json()["run_id"]

    def test_compare_200(self, client):
        c_id = self._get_run_id(client, "classical")
        q_id = self._get_run_id(client, "mock")
        r = client.get(f"/api/compare?classical_id={c_id}&quantum_id={q_id}")
        assert r.status_code == 200

    def test_compare_structure(self, client):
        c_id = self._get_run_id(client, "classical")
        q_id = self._get_run_id(client, "mock")
        data = client.get(f"/api/compare?classical_id={c_id}&quantum_id={q_id}").get_json()
        assert "classical" in data
        assert "quantum"   in data
        assert "advantage" in data

    def test_compare_missing_params_400(self, client):
        r = client.get("/api/compare")
        assert r.status_code == 400

    def test_compare_bad_id_404(self, client):
        r = client.get("/api/compare?classical_id=fake&quantum_id=also_fake")
        assert r.status_code == 404

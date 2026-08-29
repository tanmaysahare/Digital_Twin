"""The API boundary, driven against a twin with a stream we control.

The replay source is injectable, so these run without simulating a line. What
they check is the boundary rather than the arithmetic:

- A cold start is a normal condition of this product, not an error. It leaves as
  a 409 problem detail whose `detail` is a sentence with the count that would
  change the answer, and the interface shows that sentence rather than a
  spinner (UX_SPEC.md Section 9).
- No endpoint writes anywhere, and the reflection test says so over the whole
  route table rather than over the adapters alone.
- Every value in a state response carries a provenance, which is the one thing
  the `Estimate` shape exists to guarantee at the wire.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from connector.replay import ReplaySource
from twin.api.context import Context, reset_context
from twin.api.main import app
from twin.config.loader import load_line_definition, load_sensor_catalogue
from twin.live import LiveSettings, LiveTwin

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
EPOCH = datetime(2026, 3, 2, 6, 0, tzinfo=UTC)


@pytest.fixture(name="client")
def fixture_client():
    """A client against a twin whose stream is empty and never starts."""
    line = load_line_definition(CONFIG_DIR / "lines" / "line2.yaml")
    catalogue = load_sensor_catalogue(CONFIG_DIR / "catalogue" / "sensors.yaml")
    source = ReplaySource(
        line=line,
        epoch=EPOCH,
        events=(),
        description="an empty stream, for a check",
    )
    twin = LiveTwin(settings=LiveSettings(units=1), source=source)
    context = Context(twin=twin, catalogue=catalogue)
    app.dependency_overrides = {}
    from twin.api.context import get_context

    app.dependency_overrides[get_context] = lambda: context
    yield TestClient(app)
    app.dependency_overrides = {}
    reset_context()


class TestColdStart:
    def test_the_state_route_says_what_it_is_waiting_for(self, client):
        """UX_SPEC.md Section 9. A cold start is a sentence, not a spinner."""
        response = client.get("/api/v1/lines/line2/state")
        assert response.status_code == 409
        body = response.json()
        assert body["type"].endswith("insufficient-history")
        assert body["title"] == "Not enough history yet"
        assert "Building the line state" in body["detail"]
        assert "forecast cycles" in body["detail"]

    def test_a_problem_detail_is_a_problem_detail(self, client):
        """RFC 9457, with a detail written to be shown to a person."""
        response = client.get("/api/v1/lines/line9/state")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert set(body) >= {"type", "title", "status", "detail", "instance"}
        assert "line9" in body["detail"]
        assert "line2" in body["detail"]

    def test_the_line_list_answers_before_any_event_arrives(self, client):
        """Configuration is known at start-up and does not wait for a stream."""
        body = client.get("/api/v1/lines").json()
        assert len(body["lines"]) == 1
        line = body["lines"][0]
        assert line["stations"] == 42
        assert line["tiers"] == {"A": 24, "B": 12, "C": 6}
        assert len(line["zones"]) == 3
        assert len(line["gates"]) == 3

    def test_health_reports_warming_rather_than_failing(self, client):
        """A container probe gets an answer without the twin having one."""
        body = client.get("/health").json()
        assert body["status"] == "OK"
        assert body["twin"] == "WARMING"


def _leaf_routes(routes):
    """Every leaf route, including the ones inside an included router.

    FastAPI nests an included router rather than flattening it into
    `app.routes`, so walking the top level alone reaches the three
    documentation endpoints and nothing else. A boundary test that walks only
    the top level passes by seeing nothing, which is the failure mode this
    helper exists to remove.
    """
    for route in routes:
        included = getattr(route, "original_router", None)
        nested = getattr(route, "routes", None) or getattr(included, "routes", None)
        if nested:
            yield from _leaf_routes(nested)
        if getattr(route, "path", None) is not None:
            yield route


class TestBoundary:
    def test_the_walk_reaches_the_routes_that_matter(self):
        """The other two tests are worthless if this one does not hold."""
        paths = {route.path for route in _leaf_routes(app.routes)}
        assert "/api/v1/lines/{line_id}/state" in paths
        assert len(paths) > 20

    def test_no_route_offers_a_write_to_the_line(self):
        """The architectural boundary, over the whole route table."""
        forbidden = ("write", "actuate", "command", "control", "setpoint", "override")
        for route in _leaf_routes(app.routes):
            path = route.path
            assert not any(word in path.lower() for word in forbidden), path

    def test_only_three_paths_accept_a_post_and_none_applies_anything(self):
        """A counterfactual, a decision record and the business case."""
        posts = sorted(
            {
                route.path
                for route in _leaf_routes(app.routes)
                if "POST" in (getattr(route, "methods", None) or set())
            }
        )
        assert posts == [
            "/api/v1/counterfactual/{run_id}/mark-executed",
            "/api/v1/lines/{line_id}/counterfactual",
            "/api/v1/program/business-case",
        ]

    def test_the_decision_record_states_that_nothing_was_applied(self):
        """AC-034. It is in the response body, not only in the documentation.

        Checked on the response model rather than through a call, because a
        decision carries the twin's clock and a twin with no events has none.
        The cold path is the test below.
        """
        from twin.api.schemas import DecisionOut

        fields = DecisionOut.model_fields
        assert fields["applied"].default is False
        assert "no path to a control system" in fields["statement"].default

    def test_recording_a_decision_cold_is_a_sentence_rather_than_a_crash(self, client):
        """It reads the twin's clock, so it answers like every other route."""
        response = client.post(
            "/api/v1/counterfactual/0192-a-run/mark-executed",
            json={"label": "Add an operator at S20", "note": "floater at 09:34"},
        )
        assert response.status_code == 409
        assert "Building the line state" in response.json()["detail"]


class TestProvenanceAtTheWire:
    def test_the_estimate_shape_cannot_omit_a_provenance(self):
        """Every numeric value the twin produces leaves with one."""
        from twin.api.schemas import EstimateOut

        required = EstimateOut.model_json_schema()["required"]
        assert "provenance" in required
        assert "basis" in required
        assert "lo" in required and "hi" in required

    def test_an_inferred_estimate_carries_no_point_value(self):
        """Rule 3 in CLAUDE.md, expressed at the wire rather than in a renderer."""
        from twin.api.schemas import EstimateOut
        from twin.domain.estimate import Estimate, Interval

        inferred = EstimateOut.of(
            Estimate.inferred(Interval(54.0, 71.0), "bounded from the scans", 0.42),
            "s",
        )
        assert inferred.point is None
        assert inferred.lo == 54.0
        assert inferred.hi == 71.0

        measured = EstimateOut.of(
            Estimate.measured(58.4, "S20 reported its own cycle"), "s"
        )
        assert measured.point == 58.4

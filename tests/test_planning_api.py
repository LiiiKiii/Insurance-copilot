"""Offline tests for the A3 planning API boundary."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

try:
    from fastapi import HTTPException
    from fastapi.routing import APIRoute

    from api.routers.planning import (
        ChasePlanRequest,
        ImprovementAdviceRequest,
        PrioritizationRequest,
        _decode_tool_result,
        generate_chase_plan,
        generate_improvement_advice,
        prioritize_followups,
        router as planning_router,
    )
    from api.server import app, create_app
except ModuleNotFoundError as exc:
    app = None
    create_app = None
    IMPORT_ERROR = str(exc)
else:
    IMPORT_ERROR = ""


@unittest.skipUnless(
    create_app is not None,
    f"FastAPI test dependencies are unavailable: {IMPORT_ERROR}",
)
class PlanningApiTests(unittest.IsolatedAsyncioTestCase):
    class FakeTool:
        def __init__(self, payload: dict) -> None:
            self.payload = payload
            self.calls: list[dict] = []

        async def execute(self, **kwargs):
            self.calls.append(kwargs)
            return json.dumps(self.payload)

    def test_routes_are_mounted_on_application(self) -> None:
        expected = {
            "/api/planning/chase-plan",
            "/api/planning/improvement-advice",
            "/api/planning/prioritization",
        }
        router_paths = {
            route.path
            for route in planning_router.routes
            if isinstance(route, APIRoute)
        }

        self.assertEqual(router_paths, expected)
        for route in planning_router.routes:
            self.assertEqual(str(app.url_path_for(route.name)), route.path)
        self.assertEqual(
            str(app.url_path_for("prioritize_followups")),
            "/api/planning/prioritization",
        )

    async def test_chase_plan_forwards_validated_business_inputs(self) -> None:
        tool = self.FakeTool({"competition_id": "COMP-1", "weekly_plans": []})

        with patch(
            "api.routers.planning._build_chase_plan_tool",
            return_value=tool,
        ):
            result = await generate_chase_plan(
                ChasePlanRequest(agent_id="AGT001", competition_id="COMP-1"),
                SimpleNamespace(username="AGT001"),
            )

        self.assertEqual(result["competition_id"], "COMP-1")
        self.assertEqual(
            tool.calls,
            [{"agent_id": "AGT001", "competition_id": "COMP-1"}],
        )

    async def test_improvement_advice_forwards_top_n(self) -> None:
        tool = self.FakeTool({"agent_id": "AGT001", "advice": []})

        with patch(
            "api.routers.planning._build_improvement_advice_tool",
            return_value=tool,
        ):
            result = await generate_improvement_advice(
                ImprovementAdviceRequest(agent_id="AGT001", top_n=3),
                SimpleNamespace(username="AGT001"),
            )

        self.assertEqual(result, {"agent_id": "AGT001", "advice": []})
        self.assertEqual(tool.calls, [{"agent_id": "AGT001", "top_n": 3}])

    async def test_prioritization_forwards_supplied_candidate_contract(self) -> None:
        tool = self.FakeTool({"agent_id": "AGT001", "recommendations": []})
        request = PrioritizationRequest(
            agent_id="AGT001",
            objective={"open_gap": 1000},
            candidates=[{
                "candidate_id": "POL-1",
                "expected_contribution": 500,
                "urgency": 0.8,
                "actionability": 0.7,
            }],
            constraints={"top_k": 1},
        )

        with patch("api.routers.planning._build_prioritization_tool", return_value=tool):
            result = await prioritize_followups(request, SimpleNamespace(username="AGT001"))

        self.assertEqual(result["recommendations"], [])
        self.assertEqual(tool.calls[0]["agent_id"], "AGT001")
        self.assertEqual(tool.calls[0]["constraints"], {"top_k": 1})

    async def test_prioritization_rejects_cross_agent_request(self) -> None:
        request = PrioritizationRequest(
            agent_id="AGT002",
            objective={"open_gap": 1000},
            candidates=[],
        )

        with self.assertRaises(HTTPException) as raised:
            await prioritize_followups(request, SimpleNamespace(username="AGT001"))

        self.assertEqual(raised.exception.status_code, 403)

    def test_invalid_tool_payload_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            _decode_tool_result("not-json")

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(
            raised.exception.detail,
            "Planning tool returned an invalid response",
        )


if __name__ == "__main__":
    unittest.main()

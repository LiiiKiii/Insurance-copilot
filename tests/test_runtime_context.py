"""Tests for the per-message runtime context sent to the model."""

from __future__ import annotations

import unittest

from nanobot.agent.context import ContextBuilder


class RuntimeContextTests(unittest.TestCase):
    """Check that the model is told which agent_id its tools must use."""

    def test_websocket_context_names_signed_in_agent_id(self) -> None:
        context = ContextBuilder._build_runtime_context("websocket", "AGT07985")

        self.assertIn("Signed-in agent_id: AGT07985", context)

    def test_other_channels_do_not_claim_a_signed_in_agent(self) -> None:
        context = ContextBuilder._build_runtime_context("cli", "direct")

        self.assertIn("Chat ID: direct", context)
        self.assertNotIn("Signed-in agent_id", context)


if __name__ == "__main__":
    unittest.main()

"""Offline safety tests for candidate-first runtime replacement."""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from api.runtime_apply import RuntimeApplyCoordinator, RuntimeApplyError
from api.routers.config import _FEATURE_SLUGS


class FakeRuntime:
    def __init__(self, *, fail_start: bool = False, fail_stop: bool = False) -> None:
        self.fail_start, self.fail_stop = fail_start, fail_stop
        self.started = self.stopped = 0

    async def start(self) -> None:
        self.started += 1
        if self.fail_start:
            raise RuntimeError("candidate failed")

    async def stop(self) -> None:
        self.stopped += 1
        if self.fail_stop:
            raise RuntimeError("stop failed")


class BlockingStopRuntime(FakeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.stop_started, self.release_stop = asyncio.Event(), asyncio.Event()

    async def stop(self) -> None:
        self.stopped += 1
        self.stop_started.set()
        await self.release_stop.wait()


class RuntimeApplyCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_candidate_failure_preserves_old_runtime_and_is_cleaned_up(self) -> None:
        old, candidate = FakeRuntime(), FakeRuntime(fail_start=True)
        app = SimpleNamespace(state=SimpleNamespace(runtime=old))
        with self.assertRaisesRegex(RuntimeError, "candidate failed"):
            await RuntimeApplyCoordinator().replace(app, candidate)  # type: ignore[arg-type]
        self.assertIs(app.state.runtime, old)
        self.assertEqual(candidate.stopped, 1)
        self.assertEqual(old.stopped, 0)

    async def test_successful_replacement_starts_candidate_before_retiring_old(self) -> None:
        events: list[str] = []
        old, candidate = FakeRuntime(), FakeRuntime()
        original_start, original_stop = candidate.start, old.stop

        async def start() -> None:
            events.append("candidate-start")
            await original_start()

        async def stop() -> None:
            events.append("old-stop")
            await original_stop()

        candidate.start, old.stop = start, stop  # type: ignore[method-assign]
        app = SimpleNamespace(state=SimpleNamespace(runtime=old))
        await RuntimeApplyCoordinator().replace(app, candidate)  # type: ignore[arg-type]
        self.assertIs(app.state.runtime, candidate)
        self.assertEqual(events, ["candidate-start", "old-stop"])

    async def test_turn_drain_blocks_publication_and_serializes_apply(self) -> None:
        coordinator, entered, release = RuntimeApplyCoordinator(), asyncio.Event(), asyncio.Event()
        old, candidate = FakeRuntime(), FakeRuntime()
        app = SimpleNamespace(state=SimpleNamespace(runtime=old))

        async def active_turn() -> None:
            async with coordinator.turn():
                entered.set()
                await release.wait()

        turn = asyncio.create_task(active_turn())
        await entered.wait()
        replacement = asyncio.create_task(coordinator.replace(app, candidate))
        await asyncio.sleep(0)
        self.assertIs(app.state.runtime, old)
        release.set()
        await asyncio.gather(turn, replacement)
        self.assertIs(app.state.runtime, candidate)

    async def test_cancellation_during_drain_clears_gate_and_cleans_candidate(self) -> None:
        coordinator, entered, release = RuntimeApplyCoordinator(), asyncio.Event(), asyncio.Event()
        old, candidate = FakeRuntime(), FakeRuntime()
        app = SimpleNamespace(state=SimpleNamespace(runtime=old))

        async def active_turn() -> None:
            async with coordinator.turn():
                entered.set()
                await release.wait()

        turn = asyncio.create_task(active_turn())
        await entered.wait()
        replacement = asyncio.create_task(coordinator.replace(app, candidate))
        await asyncio.sleep(0)
        replacement.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await replacement
        self.assertIs(app.state.runtime, old)
        self.assertEqual(candidate.stopped, 1)
        release.set()
        await turn
        async with coordinator.turn():
            pass

    async def test_failed_old_retirement_keeps_published_candidate(self) -> None:
        coordinator, old, candidate = RuntimeApplyCoordinator(), FakeRuntime(fail_stop=True), FakeRuntime()
        app = SimpleNamespace(state=SimpleNamespace(runtime=old))
        retired = await coordinator.replace(app, candidate)  # type: ignore[arg-type]
        self.assertFalse(retired)
        self.assertIs(app.state.runtime, candidate)
        self.assertEqual(candidate.stopped, 0)
        await asyncio.sleep(0)
        self.assertEqual(len(coordinator._retirement_tasks), 0)

    async def test_cancellation_after_publication_keeps_retirement_owned_and_candidate_active(self) -> None:
        coordinator, old, candidate = RuntimeApplyCoordinator(), BlockingStopRuntime(), FakeRuntime()
        app = SimpleNamespace(state=SimpleNamespace(runtime=old))
        replacement = asyncio.create_task(coordinator.replace(app, candidate))
        await old.stop_started.wait()
        self.assertIs(app.state.runtime, candidate)
        self.assertEqual(len(coordinator._retirement_tasks), 1)
        replacement.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await replacement
        async with coordinator.turn():
            pass
        self.assertEqual(candidate.started, 1)
        self.assertEqual(candidate.stopped, 0)
        old.release_stop.set()
        await asyncio.gather(*tuple(coordinator._retirement_tasks))
        await asyncio.sleep(0)
        self.assertEqual(old.stopped, 1)
        self.assertEqual(len(coordinator._retirement_tasks), 0)

    async def test_repeated_replacements_remove_completed_retirement_tasks(self) -> None:
        coordinator = RuntimeApplyCoordinator()
        original, first, second = FakeRuntime(), FakeRuntime(), FakeRuntime()
        app = SimpleNamespace(state=SimpleNamespace(runtime=original))

        self.assertTrue(await coordinator.replace(app, first))  # type: ignore[arg-type]
        await asyncio.sleep(0)
        self.assertEqual(len(coordinator._retirement_tasks), 0)
        self.assertTrue(await coordinator.replace(app, second))  # type: ignore[arg-type]
        await asyncio.sleep(0)
        self.assertEqual(len(coordinator._retirement_tasks), 0)
        self.assertIs(app.state.runtime, second)
        self.assertEqual(original.stopped, 1)
        self.assertEqual(first.stopped, 1)

    async def test_shutdown_waits_for_owned_retirement_before_current_runtime(self) -> None:
        coordinator, old, candidate = RuntimeApplyCoordinator(), BlockingStopRuntime(), FakeRuntime()
        app = SimpleNamespace(state=SimpleNamespace(runtime=old))
        replacement = asyncio.create_task(coordinator.replace(app, candidate))
        await old.stop_started.wait()
        replacement.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await replacement
        shutdown = asyncio.create_task(coordinator.shutdown(app))
        await asyncio.sleep(0)
        self.assertEqual(candidate.stopped, 0)
        old.release_stop.set()
        await shutdown
        self.assertEqual(candidate.stopped, 1)

    async def test_shutdown_retires_current_published_runtime(self) -> None:
        old, current = FakeRuntime(), FakeRuntime()
        app = SimpleNamespace(state=SimpleNamespace(runtime=current))
        await RuntimeApplyCoordinator().shutdown(app)
        self.assertEqual(current.stopped, 1)
        self.assertEqual(old.stopped, 0)

    async def test_shutdown_refuses_apply_queued_after_shutdown_begins(self) -> None:
        coordinator, current, candidate = RuntimeApplyCoordinator(), FakeRuntime(), FakeRuntime()
        app = SimpleNamespace(state=SimpleNamespace(runtime=current))
        await coordinator.shutdown(app)
        with self.assertRaisesRegex(RuntimeApplyError, "shutting down"):
            await coordinator.replace(app, candidate)  # type: ignore[arg-type]
        self.assertEqual(candidate.started, 0)

    def test_feature_slug_catalog_is_explicit(self) -> None:
        self.assertIn("chat", _FEATURE_SLUGS)
        self.assertNotIn("unknown", _FEATURE_SLUGS)


if __name__ == "__main__":
    unittest.main()

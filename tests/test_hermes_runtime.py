"""Optional integration test against an installed Hermes checkout, without an LLM."""
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo


@unittest.skipUnless(os.environ.get("HERMES_WALL_CLOCK_INTEGRATION") == "1", "opt-in Hermes runtime test")
class HermesRuntimeTests(unittest.TestCase):
    def test_real_loader_dispatch_and_turn_context_injection(self):
        from hermes_cli.plugin_dev import _doctor_runtime
        from agent.turn_context import _collect_pre_llm_call_context, compose_user_api_content

        plugin_path = Path(__file__).parents[1]
        history = [{"role": "system", "content": (
            "Conversation started: Saturday, October 03, 2026\n"
            "Today's date (as of the last context rebuild): Saturday, October 03, 2026"
        )}, {"role": "user", "content": "What time is it?"}]
        agent = SimpleNamespace(session_id="resumed-or-compacted", model="test", platform="gateway")
        with _doctor_runtime(plugin_path) as runtime:
            self.assertEqual(runtime.registered_hooks, ("pre_llm_call",))
            callback = runtime.manager._hooks["pre_llm_call"][0]
            fake_clock = unittest.mock.Mock()
            fake_clock.now.side_effect = [
                datetime(2026, 10, 9, 23, 59, tzinfo=ZoneInfo("America/New_York")),
                datetime(2026, 10, 10, 0, 0, tzinfo=ZoneInfo("America/New_York")),
            ]
            # Exercise the production turn context collector with the real
            # isolated plugin dispatcher; fake only time and host routing.
            with patch.dict(callback.__globals__, {"datetime": fake_clock}), patch(
                "hermes_cli.lifecycle.invoke_hook", runtime.manager.invoke_hook
            ):
                for turn, expected in (("one", "6 calendar days"), ("two", "7 calendar days")):
                    context = _collect_pre_llm_call_context(
                        agent, effective_task_id="task", turn_id=turn,
                        original_user_message="What time is it?", messages=history,
                        conversation_history=history,
                    )
                    api_content = compose_user_api_content("What time is it?", "", context)
                    self.assertIn(expected, api_content)
                    self.assertEqual(api_content.count("[Wall clock at turn start:"), 1)
                    self.assertIn("What time is it?", api_content)
                    self.assertEqual(history[-1]["content"], "What time is it?")
            self.assertEqual(fake_clock.now.call_count, 2)


if __name__ == "__main__":
    unittest.main()

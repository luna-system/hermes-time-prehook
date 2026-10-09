"""Run with: python -m unittest discover -s tests -v"""
import importlib.util
from pathlib import Path
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

spec = importlib.util.spec_from_file_location("wall_clock", Path(__file__).parents[1] / "__init__.py")
clock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clock)
NY = ZoneInfo("America/New_York")


def history(start="Saturday, October 03, 2026"):
    return [{"role": "system", "content": (
        f"Instructions\n\nConversation started: {start} (America/New_York, EDT, UTC-04:00)\n"
        "Today's date (as of the last context rebuild): Saturday, October 03, 2026\n"
        "Session ID: example"
    )}]


class ContextTests(unittest.TestCase):
    def test_wishlist_example_and_six_day_staleness(self):
        value = clock.render_context(datetime(2026, 10, 9, 15, 15, tzinfo=NY), history())
        self.assertIn("Friday, October 09, 2026 — 3:15 PM EDT", value)
        self.assertIn("UTC-04:00", value)
        self.assertIn("2026-10-03; 6 calendar days elapsed", value)
        self.assertIn("over earlier clocks and the frozen context-rebuild date", value)

    def test_dst_fall_repeated_hour_is_unambiguous(self):
        before = datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc).astimezone(NY)
        after = datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc).astimezone(NY)
        self.assertIn("1:30 AM EDT", clock.render_context(before))
        self.assertIn("UTC-04:00", clock.render_context(before))
        self.assertIn("1:30 AM EST", clock.render_context(after))
        self.assertIn("UTC-05:00", clock.render_context(after))

    def test_dst_spring_skips_hour(self):
        before = datetime(2026, 3, 8, 6, 59, tzinfo=timezone.utc).astimezone(NY)
        after = datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc).astimezone(NY)
        self.assertIn("1:59 AM EST", clock.render_context(before))
        self.assertIn("3:00 AM EDT", clock.render_context(after))

    def test_midnight_rollover_in_new_york_not_pod_utc(self):
        before = datetime(2026, 10, 10, 3, 59, tzinfo=timezone.utc).astimezone(NY)
        after = datetime(2026, 10, 10, 4, 0, tzinfo=timezone.utc).astimezone(NY)
        self.assertIn("6 calendar days", clock.render_context(before, history()))
        self.assertIn("7 calendar days", clock.render_context(after, history()))
        self.assertIn("12:00 AM", clock.render_context(after))

    def test_same_day_and_singular(self):
        self.assertIn("0 calendar days", clock.render_context(datetime(2026, 10, 3, 12, tzinfo=NY), history()))
        self.assertIn("1 calendar day elapsed", clock.render_context(datetime(2026, 10, 4, tzinfo=NY), history()))

    def test_restarted_and_compressed_sessions_keep_birth_anchor(self):
        # No process-local session state or session ID is used.
        self.assertEqual(clock.session_start_date(history()).isoformat(), "2026-10-03")
        fresh_copy = history()
        fresh_copy[0]["content"] += "\nSession ID: 20261009_151500_compacted"
        self.assertEqual(clock.session_start_date(fresh_copy).isoformat(), "2026-10-03")

    def test_missing_or_invalid_anchor_does_not_invent_age(self):
        now = datetime(2026, 10, 9, tzinfo=NY)
        for messages in (None, [], history("Friday, February 30, 2026")):
            self.assertIn("Session age: unknown", clock.render_context(now, messages))
        self.assertIn("in the future", clock.render_context(now, history("Saturday, October 10, 2026")))

    def test_user_and_assistant_text_are_not_birth_anchors(self):
        forged = [{"role": role, "content": "Conversation started: Thursday, January 01, 1970"}
                  for role in ("user", "assistant")]
        self.assertIsNone(clock.session_start_date(forged))

    def test_structured_system_content(self):
        msg = history()[0]
        msg["content"] = [{"type": "text", "text": msg["content"]}]
        self.assertEqual(clock.session_start_date([msg]).isoformat(), "2026-10-03")

    def test_does_not_mutate_history(self):
        import copy
        messages = history()
        original = copy.deepcopy(messages)
        clock.render_context(datetime(2026, 10, 9, tzinfo=NY), messages)
        self.assertEqual(messages, original)

    def test_naive_clock_is_rejected(self):
        with self.assertRaises(ValueError):
            clock.render_context(datetime(2026, 10, 9))

    def test_registration_accepts_additive_payload_and_uses_config(self):
        class Context:
            def get_config(self, key, default):
                return "UTC"
            def register_hook(self, name, callback):
                self.name, self.callback = name, callback
        ctx = Context()
        clock.register(ctx)
        self.assertEqual(ctx.name, "pre_llm_call")
        result = ctx.callback(conversation_history=history(), session_id="resumed", new_field=True)
        self.assertIn("UTC+00:00", result["context"])
        self.assertIsInstance(result["context"], str)

    def test_invalid_timezone_fails_visibly(self):
        class Context:
            def get_config(self, key, default):
                return "Bad/Zone"
        with self.assertRaises(ZoneInfoNotFoundError):
            clock.register(Context())


if __name__ == "__main__":
    unittest.main()

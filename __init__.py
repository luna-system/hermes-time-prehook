"""Fresh, timezone-aware context through Hermes's supported pre_llm_call hook."""

from collections.abc import Mapping
from datetime import date, datetime
import re
from zoneinfo import ZoneInfo

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
START_LINE = re.compile(
    r"^Conversation started: (?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), "
    r"(" + "|".join(MONTHS) + r") (\d{1,2}), (\d{4})(?: \([^\r\n]*\))?\s*$",
    re.MULTILINE,
)


def _text_parts(content):
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    yield text


def session_start_date(conversation_history):
    """Use Hermes's frozen birth-date anchor, never dates in user/assistant text.

    This survives process restarts and compression when Hermes preserves its
    original anchor. Missing anchors remain unknown; we never guess from an ID
    whose embedded time could be in the pod's timezone or a compression date.
    """
    for message in conversation_history or ():
        if not isinstance(message, Mapping) or message.get("role") != "system":
            continue
        for text in _text_parts(message.get("content")):
            match = START_LINE.search(text)
            if match:
                month, day, year = match.groups()
                try:
                    return date(int(year), MONTHS.index(month) + 1, int(day))
                except ValueError:
                    continue
    return None


def render_context(now, conversation_history=None):
    """Pure renderer; now must be aware and already in the configured timezone."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Wall-clock datetime must be timezone-aware")
    offset = now.strftime("%z")
    offset = f"{offset[:3]}:{offset[3:]}"
    zone = getattr(now.tzinfo, "key", None) or now.tzname()
    hour = now.hour % 12 or 12
    clock = (
        f"[Wall clock at turn start: {WEEKDAYS[now.weekday()]}, "
        f"{MONTHS[now.month - 1]} {now.day:02d}, {now.year} — "
        f"{hour}:{now.minute:02d} {'AM' if now.hour < 12 else 'PM'} "
        f"{now.tzname()} ({zone}, UTC{offset})]"
    )
    started = session_start_date(conversation_history)
    if started is None:
        age = "[Session age: unknown; original start date unavailable]"
    else:
        days = (now.date() - started).days
        if days < 0:
            age = f"[Session began: {started.isoformat()}; start date is in the future — check clock/anchor]"
        else:
            unit = "day" if days == 1 else "days"
            age = f"[Session began: {started.isoformat()}; {days} calendar {unit} elapsed]"
    return (
        f"{clock}\n{age}\n"
        "Use this turn's wall clock over earlier clocks and the frozen context-rebuild date."
    )


def register(ctx):
    # Validate once at load time. Invalid zones / missing tzdata fail visibly
    # instead of silently falling back to a pod's UTC clock.
    timezone = ZoneInfo(ctx.get_config("timezone", "America/New_York"))

    def pre_llm_call(conversation_history=None, **kwargs):
        return {"context": render_context(datetime.now(timezone), conversation_history)}

    ctx.register_hook("pre_llm_call", pre_llm_call)

"""Small shared helpers used across DeskFlow modules."""

import random
import re
from datetime import date, datetime, timedelta

from config import PRIORITY_ORDER

_ILLEGAL_FILENAME = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def now_iso():
    """Timestamp string with second precision (stable sorting, readable)."""
    return datetime.now().isoformat(timespec="seconds")


def new_id(prefix, digits=4):
    """Collision-resistant, human-readable identifier."""
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return "{}_{}_{}".format(prefix, stamp, random.randint(10 ** (digits - 1), 10 ** digits - 1))


def clamp(value, low, high):
    return max(low, min(high, value))


def clean_tags(raw):
    """Accept a string or a list, return a de-duplicated lowercase list."""
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = raw.replace("，", ",").split(",")
    else:
        parts = []
        for item in raw:
            parts.extend(str(item).replace("，", ",").split(","))
    seen = []
    for part in parts:
        tag = part.strip().lower()
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def safe_filename(name, fallback="deskflow"):
    cleaned = _ILLEGAL_FILENAME.sub("_", str(name or "")).strip(" .")
    return cleaned or fallback


def parse_date(value):
    """Return a date from 'YYYY-MM-DD' or None."""
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def date_str(value):
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else None


def human_date(value):
    """Friendly relative label for a due date."""
    parsed = parse_date(value)
    if not parsed:
        return ""
    today = date.today()
    delta = (parsed - today).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if delta == -1:
        return "yesterday"
    if 1 < delta <= 7:
        return "in {}d".format(delta)
    if -7 <= delta < -1:
        return "{}d ago".format(-delta)
    return parsed.strftime("%b %d")


def week_bounds(reference=None):
    """Monday..Sunday range containing `reference` (defaults to today)."""
    ref = reference or date.today()
    start = ref - timedelta(days=ref.weekday())
    return start, start + timedelta(days=6)


def normalize_plan(plan, default_id_factory=None):
    """Coerce a stored plan dict into the canonical shape (or None)."""
    if not isinstance(plan, dict):
        return None
    text = str(plan.get("text", "") or "").strip()
    if not text:
        return None
    priority = str(plan.get("priority", "normal") or "normal").lower()
    if priority not in PRIORITY_ORDER:
        priority = "normal"
    plan_id = plan.get("id") or (default_id_factory() if default_id_factory else new_id("plan"))
    return {
        "id": str(plan_id),
        "text": text,
        "done": bool(plan.get("done", False)),
        "priority": priority,
        "created_at": plan.get("created_at") or now_iso(),
        "due_date": date_str(plan.get("due_date")),
        "done_at": plan.get("done_at") or None,
    }


def normalize_plans(plans):
    result = []
    seen = set()
    if not isinstance(plans, list):
        return result
    for item in plans:
        plan = normalize_plan(item)
        if not plan:
            continue
        while plan["id"] in seen:
            plan["id"] = new_id("plan")
        seen.add(plan["id"])
        result.append(plan)
    return result


def summarize(text, limit=60):
    flat = " ".join(str(text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "…"

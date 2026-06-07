import re
from datetime import datetime, timedelta
from typing import Any


DATE_RE = re.compile(r"(?P<year>20\d{2})[.\-/년\s]+(?P<month>\d{1,2})[.\-/월\s]+(?P<day>\d{1,2})")
TIME_RE = re.compile(r"(?P<hour>\d{1,2})\s*[:시]\s*(?P<minute>\d{2})?")


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def parse_date(value: Any) -> str:
    text = _clean_text(value)
    match = DATE_RE.search(text)
    if not match:
        return ""
    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return ""


def parse_time_range(value: Any) -> tuple[str, str, bool]:
    text = _clean_text(value)
    matches = list(TIME_RE.finditer(text))
    if len(matches) < 2:
        return "", "", False

    def fmt(match: re.Match, *, allow_24: bool = False) -> tuple[str, bool]:
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)
        if allow_24 and hour == 24 and minute == 0:
            return "00:00", True
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return "", False
        return f"{hour:02d}:{minute:02d}", False

    start_time, _ = fmt(matches[0])
    end_time, end_next_day = fmt(matches[1], allow_24=True)
    return start_time, end_time, end_next_day


def parse_datetime_range(date_str: Any, time_range_str: Any) -> tuple[str, str]:
    date = parse_date(date_str)
    start_time, end_time, end_next_day = parse_time_range(time_range_str)
    if not date or not start_time or not end_time:
        return "", ""
    start_date = datetime.fromisoformat(date).date()
    end_date = start_date + timedelta(days=1) if end_next_day else start_date
    return f"{start_date.isoformat()}T{start_time}:00", f"{end_date.isoformat()}T{end_time}:00"


def quality_status(errors: list[str], warnings: list[str] | None = None) -> str:
    warnings = warnings or []
    if errors:
        return "invalid"
    if warnings:
        return "partial"
    return "valid"


def validate_mentoring(item: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    title = _clean_text(item.get("title"))
    status = _clean_text(item.get("status"))
    start_at, end_at = parse_datetime_range(item.get("dateStr"), item.get("timeRangeStr"))

    if not _clean_text(item.get("id")):
        errors.append("missing_id")
    if not title:
        errors.append("missing_title")
    if not status:
        warnings.append("missing_status")
    if not start_at or not end_at:
        warnings.append("unparsed_schedule")

    return {
        "qualityStatus": quality_status(errors, warnings),
        "validationErrors": errors,
        "validationWarnings": warnings,
        "startAt": start_at,
        "endAt": end_at,
        "canonicalText": " ".join(
            part
            for part in [
                title,
                _clean_text(item.get("author")),
                _clean_text(item.get("dateStr")),
                _clean_text(item.get("timeRangeStr")),
                _clean_text(item.get("description")),
                _clean_text(item.get("location")),
                _clean_text(item.get("deliveryMethod")),
            ]
            if part
        ),
    }


def validate_calendar_event(item: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    title = _clean_text(item.get("title"))
    start_at, end_at = parse_datetime_range(item.get("dateStr"), item.get("timeRangeStr"))

    if not _clean_text(item.get("id")):
        errors.append("missing_id")
    if not title:
        errors.append("missing_title")
    if not start_at or not end_at:
        errors.append("unparsed_schedule")

    return {
        "qualityStatus": quality_status(errors, warnings),
        "validationErrors": errors,
        "validationWarnings": warnings,
        "startAt": start_at,
        "endAt": end_at,
        "canonicalText": " ".join(
            part
            for part in [title, _clean_text(item.get("author")), _clean_text(item.get("status"))]
            if part
        ),
    }


def validate_team(item: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if not _clean_text(item.get("teamName")):
        errors.append("missing_team_name")
    if not _clean_text(item.get("mentorName")):
        warnings.append("missing_mentor_name")
    if not item.get("members"):
        warnings.append("missing_members")
    return {
        "qualityStatus": quality_status(errors, warnings),
        "validationErrors": errors,
        "validationWarnings": warnings,
        "canonicalText": " ".join(
            part
            for part in [
                _clean_text(item.get("teamName")),
                _clean_text(item.get("leader")),
                _clean_text(item.get("mentorName")),
                _clean_text(item.get("projectName")),
                _clean_text(item.get("ictCategoryLarge")),
                _clean_text(item.get("ictCategoryMedium")),
            ]
            if part
        ),
    }


def validate_user_info(item: dict | None) -> dict:
    if not item:
        return {
            "qualityStatus": "invalid",
            "validationErrors": ["missing_user_info"],
            "validationWarnings": [],
            "canonicalText": "",
        }
    errors: list[str] = []
    warnings: list[str] = []
    if not _clean_text(item.get("name")):
        errors.append("missing_name")
    if not _clean_text(item.get("role")):
        warnings.append("missing_role")
    return {
        "qualityStatus": quality_status(errors, warnings),
        "validationErrors": errors,
        "validationWarnings": warnings,
        "canonicalText": " ".join(
            part
            for part in [
                _clean_text(item.get("name")),
                _clean_text(item.get("email")),
                _clean_text(item.get("role")),
                ", ".join(item.get("techStacks", [])) if isinstance(item.get("techStacks"), list) else _clean_text(item.get("techStacks")),
            ]
            if part
        ),
    }

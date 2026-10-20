"""Classify Garmin activity summaries."""
from .config import NO_GPS_TYPES


def is_run(act):
    key = ((act.get("activityType") or {}).get("typeKey") or "").lower()
    return "run" in key


def type_key(act):
    return ((act.get("activityType") or {}).get("typeKey") or "").lower()


def has_gps(act):
    k = type_key(act)
    if any(t in k for t in NO_GPS_TYPES):
        return False
    if act.get("hasPolyline") is False:
        return False
    return True

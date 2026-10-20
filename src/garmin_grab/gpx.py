"""GPX parsing and resampling into the compact runs.json stream."""
import math
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from .config import SAMPLE_EVERY_S


def _tag(el):
    return el.tag.rsplit("}", 1)[-1]


def _parse_time(s):
    s = s.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def haversine(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def parse_gpx(data):
    """Return list of (t_epoch, lat, lon, ele|None, hr|None)."""
    root = ET.fromstring(data)
    pts = []
    for el in root.iter():
        if _tag(el) != "trkpt":
            continue
        try:
            lat, lon = float(el.get("lat")), float(el.get("lon"))
        except (TypeError, ValueError):
            continue
        t = ele = hr = None
        for c in el.iter():
            name = _tag(c)
            if not c.text:
                continue
            if name == "time":
                t = _parse_time(c.text)
            elif name == "ele":
                ele = float(c.text)
            elif name == "hr":
                hr = int(float(c.text))
        if t is not None:
            pts.append((t, lat, lon, ele, hr))
    pts.sort(key=lambda p: p[0])
    return pts


def to_stream(pts, summary_distance=None):
    """Cumulative distance on all points, then sample every SAMPLE_EVERY_S seconds."""
    if len(pts) < 2:
        return None
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + haversine(a[1], a[2], b[1], b[2]))
    total = cum[-1]
    scale = 1.0
    if summary_distance and total > 0:
        ratio = summary_distance / total
        if 0.85 < ratio < 1.15:          # align with Garmin's own distance
            scale = ratio
    t0 = pts[0][0]
    T, D, H, E = [], [], [], []
    last_t = None
    for i, p in enumerate(pts):
        if last_t is not None and p[0] - last_t < SAMPLE_EVERY_S and i != len(pts) - 1:
            continue
        last_t = p[0]
        T.append(int(round(p[0] - t0)))
        D.append(int(round(cum[i] * scale)))
        H.append(p[4] or 0)
        E.append(int(round(p[3] * 10)) if p[3] is not None else 0)
    return {"t": T, "d": D, "hr": H, "e": E}

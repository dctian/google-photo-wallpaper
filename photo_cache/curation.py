"""Private, local approximations of useful photo-frame selection rules.

These are simple image statistics, not Google's curation model. In particular,
they cannot identify smiles, important people, screenshots, or sensitive content.
"""

from __future__ import annotations

import calendar
import io
import math
import random
import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Any


def _capture_date(photo) -> date | None:
    stamp = getattr(photo, "taken_at_ms", None)
    offset = getattr(photo, "timezone_offset_ms", None)
    if type(stamp) is not int:
        return None
    try:
        if type(offset) is int:
            # Preserve the date where the picture was taken, including near
            # midnight. An unknown capture offset falls back to this PC's zone.
            return (datetime(1970, 1, 1, tzinfo=timezone.utc)
                    + timedelta(milliseconds=stamp + offset)).date()
        return datetime.fromtimestamp(stamp / 1000).date()
    except (ValueError, OverflowError, OSError):
        return None


def _anniversary_distance(photo, today: date) -> int | None:
    taken = _capture_date(photo)
    if taken is None or taken.year >= today.year:
        return None
    # A Feb 29 anniversary is observed on Feb 28 during a non-leap year.
    day = min(taken.day, calendar.monthrange(today.year, taken.month)[1])
    anniversary = date(today.year, taken.month, day)
    distance = abs((anniversary - today).days)
    year_days = 366 if calendar.isleap(today.year) else 365
    return min(distance, year_days - distance)


def _metadata_preference(photo, config) -> float:
    width, height = getattr(photo, "width", 0), getattr(photo, "height", 0)
    if not (type(width) is int and type(height) is int and width > 0 and height > 0):
        return 0.0
    long_edge, short_edge = max(width, height), min(width, height)
    resolution = min(1.0, long_edge / max(1, getattr(config, "min_long_edge", 1600)))
    resolution *= min(1.0, short_edge / max(1, getattr(config, "min_short_edge", 720)))
    # Small preference only: portrait pictures still belong in collages.
    target = getattr(config, "max_width", 3840) / max(1, getattr(config, "max_height", 2160))
    aspect_match = 1 / (1 + abs(math.log((width / height) / target)))
    return 0.85 * resolution + 0.15 * aspect_match


def rank_candidates(candidates: list[tuple[str, Any]], history: dict,
                    config, today: date | None = None) -> list[tuple[str, Any]]:
    """Order all candidates with fair rotation and an anniversary batch quota.

    Photos never selected come first within each pool, followed by those last
    selected longest ago. Metadata breaks ties without excluding small images.
    Each batch reserves the configured fraction for nearby anniversaries; either
    pool fills unused slots. The original candidates are never mutated.
    """
    today = today or date.today()
    batch_size = max(1, int(getattr(config, "batch_size", 100)))
    fraction = max(0.0, min(1.0, float(getattr(config, "anniversary_fraction", 0.3))))
    window = max(0, min(183, int(getattr(config, "anniversary_window_days", 7))))
    quality = bool(getattr(config, "quality_filter", True))
    working = list(candidates)
    random.SystemRandom().shuffle(working)
    distances = {key: _anniversary_distance(photo, today) for key, photo in working}

    def order(pair):
        key, photo = pair
        selected = history.get(key)
        seen = type(selected) in (int, float) and math.isfinite(selected)
        return (seen, selected if seen else 0,
                distances[key] if fraction > 0 and distances[key] is not None and distances[key] <= window else 184,
                -_metadata_preference(photo, config) if quality else 0)

    working.sort(key=order)
    if fraction == 0:
        return working
    anniversary = [pair for pair in working if distances[pair[0]] is not None
                   and distances[pair[0]] <= window]
    general = [pair for pair in working if distances[pair[0]] is None
               or distances[pair[0]] > window]
    output = []
    ai = gi = 0
    while ai < len(anniversary) or gi < len(general):
        size = min(batch_size, len(anniversary) - ai + len(general) - gi)
        anniversary_count = min(len(anniversary) - ai, int(size * fraction + 0.5))
        general_count = min(len(general) - gi, size - anniversary_count)
        anniversary_count = min(len(anniversary) - ai, size - general_count)
        total = anniversary_count + general_count
        added_anniversary = 0
        for position in range(total):
            desired = (position + 1) * anniversary_count // total
            if desired > added_anniversary:
                output.append(anniversary[ai])
                ai += 1
                added_anniversary += 1
            else:
                output.append(general[gi])
                gi += 1
    return output


def analyze_image(jpeg: bytes) -> dict:
    """Compute cheap statistics and a difference hash entirely on this laptop.

    A low-texture picture may be an excellent portrait or landscape;
    low texture alone is never treated as blur.
    """
    from PIL import Image, ImageOps, ImageStat

    with Image.open(io.BytesIO(jpeg)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    width, height = image.size
    image.thumbnail((256, 256), Image.Resampling.LANCZOS)
    gray = image.convert("L")
    stats = ImageStat.Stat(gray)
    mean = stats.mean[0] / 255.0
    contrast = stats.stddev[0] / 255.0
    pixels = gray.tobytes()
    tw, th = gray.size
    gradients = []
    for y in range(th):
        start = y * tw
        for x in range(tw - 1):
            gradients.append(abs(pixels[start + x + 1] - pixels[start + x]))
    for y in range(th - 1):
        start = y * tw
        for x in range(tw):
            gradients.append(abs(pixels[start + x + tw] - pixels[start + x]))
    edge_strength = sum(gradients) / max(1, len(gradients)) / 255.0
    histogram = gray.histogram()
    dark = sum(histogram[:8]) / len(pixels)
    light = sum(histogram[248:]) / len(pixels)
    small = gray.resize((9, 8), Image.Resampling.LANCZOS).tobytes()
    difference = 0
    for y in range(8):
        for x in range(8):
            difference = (difference << 1) | (small[y * 9 + x + 1] > small[y * 9 + x])
    bits = difference.bit_count()
    color = [round(value / 255.0, 5) for value in ImageStat.Stat(image).mean]
    return {
        "dhash": f"{difference:016x}",
        "brightness": round(mean, 5),
        "contrast": round(contrast, 5),
        "edge_strength": round(edge_strength, 5),
        "mean_rgb": color,
        "aspect_ratio": round(width / height, 5),
        "hash_reliable": contrast >= 0.04 and edge_strength >= 0.01 and 4 <= bits <= 60,
        # Only nearly blank black/white frames qualify for automatic skipping.
        # Blur or low texture alone is deliberately not a rejection criterion.
        "low_quality": max(dark, light) > 0.995 and contrast < 0.015,
    }


def near_duplicate(hash_a: str | Mapping, hash_b: str | Mapping) -> bool:
    """Conservative dHash comparison; pass full analysis dicts for extra guards."""
    if isinstance(hash_a, Mapping) and isinstance(hash_b, Mapping):
        if not hash_a.get("hash_reliable") or not hash_b.get("hash_reliable"):
            return False
        try:
            if abs(hash_a["brightness"] - hash_b["brightness"]) > 0.08:
                return False
            if max(abs(a - b) for a, b in zip(hash_a["mean_rgb"], hash_b["mean_rgb"], strict=True)) > 0.12:
                return False
            if abs(math.log(hash_a["aspect_ratio"] / hash_b["aspect_ratio"])) > 0.12:
                return False
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return False
        hash_a, hash_b = hash_a.get("dhash"), hash_b.get("dhash")
    if not all(isinstance(value, str) and re.fullmatch(r"[a-fA-F0-9]{16}", value)
               for value in (hash_a, hash_b)):
        return False
    a, b = int(hash_a, 16), int(hash_b, 16)
    # Blank images/gradients often have the same degenerate all-zero/one hash.
    if not (4 <= a.bit_count() <= 60 and 4 <= b.bit_count() <= 60):
        return False
    return (a ^ b).bit_count() <= 3

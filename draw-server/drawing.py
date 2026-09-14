"""Validated paper coordinates and ordered, uncalibrated Ender 3 pen paths."""

from dataclasses import asdict, dataclass
import json
import math
from uuid import UUID

PAPER_WIDTH_MM = 215.9
PAPER_HEIGHT_MM = 279.4
MAX_LENGTH_MM = 609.6
MAX_STROKES = 200
MAX_POINTS = 20_000


class InvalidDrawing(ValueError):
    pass


def validate_drawing(data):
    if not isinstance(data, dict) or set(data) != {"version", "submission_id", "strokes"}:
        raise InvalidDrawing("Expected version, submission_id, and strokes only.")
    if type(data["version"]) is not int or data["version"] != 1:
        raise InvalidDrawing("Unsupported drawing version.")
    try:
        submission_id = str(UUID(data["submission_id"]))
    except (ValueError, TypeError, AttributeError):
        raise InvalidDrawing("submission_id must be a UUID.") from None
    strokes = data["strokes"]
    if not isinstance(strokes, list) or not 1 <= len(strokes) <= MAX_STROKES:
        raise InvalidDrawing(f"Include 1 to {MAX_STROKES} strokes.")
    result, lengths, count = [], [], 0
    for stroke in strokes:
        if not isinstance(stroke, list) or not stroke:
            raise InvalidDrawing("Every stroke must have at least one point.")
        count += len(stroke)
        if count > MAX_POINTS:
            raise InvalidDrawing(f"Drawings may contain at most {MAX_POINTS} points.")
        clean = []
        for point in stroke:
            if not isinstance(point, list) or len(point) != 2:
                raise InvalidDrawing("Each point must be [x_mm, y_mm].")
            if any(type(n) not in (int, float) for n in point):
                raise InvalidDrawing("Coordinates must be numbers.")
            x, y = point
            if not (0 <= x <= PAPER_WIDTH_MM and 0 <= y <= PAPER_HEIGHT_MM):
                raise InvalidDrawing("Coordinates must be finite and within the paper.")
            x, y = float(x), float(y)
            clean.append([0.0 if x == 0 else x, 0.0 if y == 0 else y])
            if len(clean) > 1:
                lengths.append(math.dist(clean[-2], clean[-1]))
        result.append(clean)
    length = math.fsum(lengths)
    if length > MAX_LENGTH_MM + 1e-6:
        raise InvalidDrawing("The drawing exceeds the 24-inch pen length limit.")
    canonical = json.dumps({"version": 1, "strokes": result}, separators=(",", ":"), allow_nan=False)
    return submission_id, result, length, canonical


@dataclass(frozen=True)
class PrinterConfig:
    bed_width_mm: float = 220.0
    bed_height_mm: float = 220.0
    margin_mm: float = 10.0
    drawing_height_mm: float = 200.0
    contact_z_mm: float = 0.0
    lifted_z_mm: float = 3.0
    travel_feed_mm_min: float = 3000.0
    drawing_feed_mm_min: float = 1200.0
    z_feed_mm_min: float = 300.0
    dot_dwell_ms: int = 100

    def __post_init__(self):
        for value in asdict(self).values():
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Printer settings must be finite numbers.")
        if not (1 <= self.bed_width_mm <= 1000 and 1 <= self.bed_height_mm <= 1000):
            raise ValueError("Invalid printer bed dimensions.")
        if not (0 <= self.margin_mm < min(self.bed_width_mm, self.bed_height_mm) / 2):
            raise ValueError("The margin must leave usable bed space.")
        if not 1 <= self.drawing_height_mm <= 1000:
            raise ValueError("Invalid drawing height.")
        if not 0 <= self.contact_z_mm < self.lifted_z_mm <= 250:
            raise ValueError("Require 0 <= contact Z < lifted Z <= 250 mm.")
        if not all(1 <= f <= 6000 for f in (self.travel_feed_mm_min, self.drawing_feed_mm_min, self.z_feed_mm_min)):
            raise ValueError("Feed rates must be between 1 and 6000 mm/min.")
        if type(self.dot_dwell_ms) is not int or not 0 <= self.dot_dwell_ms <= 1000:
            raise ValueError("Dot dwell must be an integer between 0 and 1000 ms.")

    @property
    def scale(self):
        return min(self.drawing_height_mm / PAPER_HEIGHT_MM,
                   (self.bed_width_mm - 2 * self.margin_mm) / PAPER_WIDTH_MM,
                   (self.bed_height_mm - 2 * self.margin_mm) / PAPER_HEIGHT_MM)

    def transform(self, point):
        scale = self.scale
        x_offset = (self.bed_width_mm - PAPER_WIDTH_MM * scale) / 2
        y_offset = (self.bed_height_mm - PAPER_HEIGHT_MM * scale) / 2
        return x_offset + point[0] * scale, y_offset + (PAPER_HEIGHT_MM - point[1]) * scale


def generate_gcode(strokes, config):
    """Call only after validate_drawing. No rasterization, reordering, or extrusion."""
    lines = [
        "; PEN PLOT - PENDING CALIBRATION - NOT READY FOR UNATTENDED EXECUTION",
        "; Home the printer BEFORE mounting the pen; this file does not home or set an origin.",
        "; Calibrate the absolute contact Z and lifted Z for the mounted pen and paper.",
        "; Verify clear travel and bed bounds; disable leveling (M420 S0 below).",
        "; Secure a flat sheet; test with pen lifted first. No printer is connected by this service.",
        f"; Letter page scaled uniformly by {config.scale:.9f}; source origin is upper left.",
        "M104 S0", "M140 S0", "M107", "G21", "G90", "M420 S0",
        f"G0 Z{config.lifted_z_mm:.4f} F{config.z_feed_mm_min:.1f}",
    ]
    for index, stroke in enumerate(strokes, 1):
        lines.append(f"; Stroke {index}")
        x, y = config.transform(stroke[0])
        lines += [f"G0 X{x:.4f} Y{y:.4f} F{config.travel_feed_mm_min:.1f}",
                  f"G1 Z{config.contact_z_mm:.4f} F{config.z_feed_mm_min:.1f}"]
        for point in stroke[1:]:
            x, y = config.transform(point)
            lines.append(f"G1 X{x:.4f} Y{y:.4f} F{config.drawing_feed_mm_min:.1f}")
        if len(stroke) == 1 or all(point == stroke[0] for point in stroke):
            lines.append(f"G4 P{config.dot_dwell_ms}")
        lines.append(f"G0 Z{config.lifted_z_mm:.4f} F{config.z_feed_mm_min:.1f}")
    lines += ["M400", "; End: pen lifted; motors remain enabled to preserve the calibrated position."]
    return "\n".join(lines) + "\n"

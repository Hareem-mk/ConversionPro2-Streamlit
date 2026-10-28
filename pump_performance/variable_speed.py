"""Speed-scaled supplied curves and bounded system intersections; no Streamlit."""
from dataclasses import dataclass
from .affinity_laws import calculate_speed_affinity
from .pump_curve import create_pump_curve, PumpCurve
from .operating_point import find_operating_points, OperatingPointResult
from .system_sensitivity import NumericChange, numeric_change, is_unique

NO_SCALED_POINT = 'No valid operating point exists within the affinity-scaled pump-curve range.'

@dataclass(frozen=True)
class VariableSpeedCurveResult:
    reference_speed_rpm: float
    new_speed_rpm: float
    ratio: float
    speed_change_percent: float
    scaled_curve: PumpCurve

@dataclass(frozen=True)
class VariableSpeedOperatingPointResult:
    scaling: VariableSpeedCurveResult
    base: OperatingPointResult
    new: OperatingPointResult
    flow_change: NumericChange | None
    head_change: NumericChange | None


def scale_head_curve_by_speed(reference_curve, reference_speed_rpm, new_speed_rpm):
    # All ratio, speed validation and Q/H scaling belong to Phase 3I.
    speed = calculate_speed_affinity(0, 0, 0, reference_speed_rpm, new_speed_rpm)
    points = []
    for point in reference_curve.points:
        result = calculate_speed_affinity(point.flow_m3_s, point.head_m, 0,
                                          reference_speed_rpm, new_speed_rpm)
        points.append((result.estimated_flow_m3_s, result.estimated_head_m))
    scaled = create_pump_curve(points, 'm³/s', 'm', {'m³/s': 1.0})
    return VariableSpeedCurveResult(float(reference_speed_rpm), float(new_speed_rpm),
        speed.ratio, numeric_change(reference_speed_rpm, new_speed_rpm).percent, scaled)


def evaluate_variable_speed_operating_point(reference_curve, reference_speed_rpm,
                                            new_speed_rpm, system_curve):
    scaling = scale_head_curve_by_speed(reference_curve, reference_speed_rpm, new_speed_rpm)
    base = find_operating_points(reference_curve, system_curve)
    new = find_operating_points(scaling.scaled_curve, system_curve)
    unique = is_unique(base) and is_unique(new)
    return VariableSpeedOperatingPointResult(scaling, base, new,
        numeric_change(base.points[0].flow_m3_s, new.points[0].flow_m3_s) if unique else None,
        numeric_change(base.points[0].head_m, new.points[0].head_m) if unique else None)

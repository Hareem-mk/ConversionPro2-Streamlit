"""Phase 3G: bounded intersections of the validated pump and system kernels."""
from dataclasses import dataclass
import math

from .pump_curve import PumpCurve, interpolate_pump_head

HEAD_ABS_TOL_M = 1e-9
HEAD_REL_TOL = 1e-10
FLOW_ABS_TOL_M3_S = 1e-14
FLOW_REL_TOL = 1e-12
NO_INTERSECTION = 'No pump/system intersection exists within the supplied pump-curve range.'
MULTIPLE_INTERSECTIONS = 'Multiple pump/system intersections were found within the supplied curve range.'


@dataclass(frozen=True)
class OperatingPoint:
    flow_m3_s: float
    head_m: float
    pump_head_m: float
    system_head_m: float
    residual_m: float


@dataclass(frozen=True)
class CoincidentInterval:
    minimum_flow_m3_s: float
    maximum_flow_m3_s: float
    head_m: float


@dataclass(frozen=True)
class OperatingPointResult:
    points: tuple[OperatingPoint, ...]
    coincident_intervals: tuple[CoincidentInterval, ...] = ()


def head_tolerance(pump_head_m, system_head_m):
    return HEAD_ABS_TOL_M + HEAD_REL_TOL * max(abs(pump_head_m), abs(system_head_m))


def _evaluate(curve_si, model, flow):
    # The SI view avoids a display-unit round trip in the root solver. It shares
    # the unchanged validated points and uses the original 3E interpolation.
    pump = interpolate_pump_head(curve_si, flow).head_m
    system = model.at_flow(flow).total_head_m
    return OperatingPoint(flow, pump, pump, system, pump - system)


def _numerically_zero(point):
    # Root discovery uses roundoff scale, tighter than residual verification.
    return abs(point.residual_m) <= 8 * math.ulp(max(point.pump_head_m, point.system_head_m))


def _bisect(curve_si, model, left, right):
    # Endpoints already bracket a root on a monotone subinterval. Never leave it.
    for _ in range(2200):
        mid = left.flow_m3_s + (right.flow_m3_s - left.flow_m3_s) / 2
        if mid == left.flow_m3_s or mid == right.flow_m3_s:
            return min((left, right), key=lambda p: abs(p.residual_m))
        point = _evaluate(curve_si, model, mid)
        if point.residual_m == 0:
            return point
        if (point.residual_m < 0) == (left.residual_m < 0):
            left = point
        else:
            right = point
    raise ValueError('Operating-point root search did not converge within the supported numeric range.')


def _segment_vertex(lower, upper, k_si):
    # d(H_pump-H_system)/dQ = segment slope - 2KQ. This is only
    # a partition location; heads/residuals always use the shared kernels.
    dh = upper.head_m - lower.head_m
    if k_si == 0 or dh <= 0:
        return None
    dq = upper.flow_m3_s - lower.flow_m3_s
    vertex = (0.5 * (dh / dq)) / k_si
    if not math.isfinite(vertex) or vertex == 0:
        exponent = math.log(dh) - math.log(dq) - math.log(k_si) - math.log(2)
        try:
            vertex = math.exp(exponent)
        except OverflowError:
            return None
    return vertex if lower.flow_m3_s < vertex < upper.flow_m3_s else None


def find_operating_points(curve, model):
    """Return all isolated roots and any coincident intervals, in SI flow order.

    Search every supplied pump segment. Split at the possible quadratic
    extremum, then use bounded bisection on sign-changing monotone pieces.
    Roundoff-level endpoint/extremum contacts detect tangencies without a sign
    change. Every result is range-checked and independently residual-checked.
    """
    model.at_flow(0)  # Reuse 3F validation, including K and static head.
    if len(curve.points) < 3:
        raise ValueError('Use a validated pump curve with at least 3 unique Q–H points.')
    curve_si = PumpCurve(curve.points, 'm³/s', 'm', 1.0, 1.0)
    flow_tol = FLOW_ABS_TOL_M3_S + FLOW_REL_TOL * max(abs(p.flow_m3_s) for p in curve.points)
    candidates, coincident = [], []
    for lower, upper in zip(curve.points, curve.points[1:]):
        if lower.flow_m3_s >= upper.flow_m3_s:
            raise ValueError('Use the validated, sorted pump-curve data model.')
        if model.k_si == 0 and lower.head_m == upper.head_m == model.static_head_m:
            if coincident and coincident[-1].maximum_flow_m3_s == lower.flow_m3_s:
                previous = coincident.pop()
                coincident.append(CoincidentInterval(previous.minimum_flow_m3_s, upper.flow_m3_s, lower.head_m))
            else:
                coincident.append(CoincidentInterval(lower.flow_m3_s, upper.flow_m3_s, lower.head_m))
            continue
        flows = [lower.flow_m3_s, upper.flow_m3_s]
        vertex = _segment_vertex(lower, upper, model.k_si)
        if vertex is not None:
            flows.insert(1, vertex)
        evaluated = [_evaluate(curve_si, model, q) for q in flows]
        contacts = [_numerically_zero(p) for p in evaluated]
        candidates.extend(p for p, contact in zip(evaluated, contacts) if contact)
        for index, (left, right) in enumerate(zip(evaluated, evaluated[1:])):
            if not contacts[index] and not contacts[index + 1] and (left.residual_m < 0) != (right.residual_m < 0):
                candidates.append(_bisect(curve_si, model, left, right))
    validated = []
    for point in sorted(candidates, key=lambda p: p.flow_m3_s):
        if not curve.points[0].flow_m3_s <= point.flow_m3_s <= curve.points[-1].flow_m3_s:
            raise ValueError('Operating-point candidate lies outside the supplied curve range.')
        if abs(point.residual_m) > head_tolerance(point.pump_head_m, point.system_head_m):
            raise ValueError('Pump and system heads do not agree within the operating-point tolerance.')
        if any(interval.minimum_flow_m3_s - flow_tol <= point.flow_m3_s <= interval.maximum_flow_m3_s + flow_tol
               for interval in coincident):
            continue
        if validated and point.flow_m3_s - validated[-1].flow_m3_s <= flow_tol:
            if abs(point.residual_m) < abs(validated[-1].residual_m):
                validated[-1] = point
        else:
            validated.append(point)
    return OperatingPointResult(tuple(validated), tuple(coincident))

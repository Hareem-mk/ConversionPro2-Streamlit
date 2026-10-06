"""Stage 2D: documented representative K and explicitly based minor losses."""
from dataclasses import dataclass
import math
from advanced_engineering import G, minor_loss
from .pipe_capacity import nonnegative
from .pipe_geometry import positive

SOURCE = 'https://usepa.github.io/EPANET2.2/3_network_model.html'
CAUTION = ('K coefficients depend on geometry and operating condition. Representative database '
           'values should be replaced by manufacturer/project-specific data when available. '
           'Confirm velocity basis, valve opening, diameter ratios and tee flow path; '
           'this is not a branching-network solver.')


@dataclass(frozen=True)
class KRecord:
    id: str
    component: str
    configuration: str
    condition: str
    k: float
    source: str
    edition: str
    location: str
    url: str
    velocity_basis: str
    limitations: str


def _record(id, component, config, condition, k):
    return KRecord(id,component,config,condition,k,'US EPA, EPANET Users Manual',
        'Release 2.2 (2020), EPA/600/R-20/133','Section 3.1, Minor Losses; Table 3.3',SOURCE,
        'Mean velocity of the pipe to which the loss coefficient is assigned in the EPANET model. '
        'Detailed upstream/downstream or tee area-ratio basis is not supplied by Table 3.3.',
        'Only the named representative configuration is documented. Detailed dimensions, '
        'diameter ratios, connection style, Reynolds range and manufacturer are not specified. '
        'Tees require engineer verification of the selected flow path and reference velocity; '
        'do not combine losses on different flow paths. ' + CAUTION)


K_RECORDS = (
    _record('globe_open','Globe valve','Globe valve; internal geometry unspecified','Fully open',10.0),
    _record('angle_open','Angle valve','Angle valve; internal geometry unspecified','Fully open',5.0),
    _record('swing_open','Swing check valve','Swing check; internal geometry unspecified','Fully open',2.5),
    _record('gate_open','Gate valve','Gate valve; internal geometry unspecified','Fully open',.2),
    _record('elbow45','45 degree elbow','45° turn; radius and connection unspecified','Not specified by table',.4),
    _record('tee_run','Standard tee — flow through run','Standard tee; flow through run','Flow split/combining condition not specified',.6),
    _record('tee_branch','Standard tee — flow through branch','Standard tee; flow through branch','Flow split/combining condition not specified',1.8),
)


@dataclass(frozen=True)
class Component:
    quantity: int
    k: float
    velocity: float | None = None
    counted_as_equivalent_length: bool = False


def quantity(value):
    n=nonnegative(value,'Quantity')
    if not n.is_integer() or n > 2**53-1:
        raise ValueError('Quantity must be an exactly representable nonnegative integer.')
    return int(n)


def _validated(rows):
    if not rows:
        raise ValueError('At least one component row is required.')
    result=[]
    for row in rows:
        n=quantity(row.quantity);k=nonnegative(row.k,'K')
        if row.counted_as_equivalent_length and n > 0:
            raise ValueError('Double counting: remove this K row or its equivalent-length loss.')
        nk=n*k
        if not math.isfinite(nk):raise ValueError('Quantity × K exceeds numeric range.')
        result.append((n,k,nk,row.velocity))
    return result


def _sum(values):
    try: result=math.fsum(values)
    except OverflowError:raise ValueError('Total exceeds numeric range.') from None
    if not math.isfinite(result):raise ValueError('Total exceeds numeric range.')
    return result


def _head(k,v):
    # Head is density-independent. The API requires a positive density, so use
    # a computational reference with rho_ref * G == 1 to preserve the head-only
    # numeric range. Discard its pressure: this is NOT an assumed fluid density.
    # Actual pressure outputs below still require the engineer's supplied rho.
    try:
        return minor_loss(k,v,1/G).head_m
    except ValueError:
        raise ValueError('Head loss exceeds numeric range.') from None


def calculate_fittings(rows, *, mode, common_basis_confirmed=False, velocity=None, density=None):
    values=_validated(rows)
    rho=None if density is None else positive(density,'Density')
    if mode == 'common':
        if not common_basis_confirmed:
            raise ValueError('Confirm all K values share the same reference velocity and flow path.')
        if any(row.velocity is not None for row in rows):
            raise ValueError('Per-row velocities require separate-velocity mode.')
        k_total=_sum(x[2] for x in values)
        if velocity is None:
            if rho is not None:raise ValueError('Velocity is required for pressure loss.')
            return dict(k_total=k_total,head_m=None,pressure_pa=None,pressure_kpa=None,pressure_bar=None,rows=[])
        v=nonnegative(velocity,'Common reference velocity')
        row_heads=[_head(nk,v) for _,_,nk,_ in values]
        pressure=None if rho is None else minor_loss(k_total,v,rho).pressure_pa
        head=_head(k_total,v)
    elif mode == 'separate':
        if velocity is not None:raise ValueError('Do not supply a common velocity in separate-velocity mode.')
        k_total=None
        row_heads=[];pressures=[]
        for _,_,nk,row_v in values:
            v=nonnegative(row_v,'Row reference velocity')
            row_heads.append(_head(nk,v))
            if rho is not None:pressures.append(minor_loss(nk,v,rho).pressure_pa)
        head=_sum(row_heads);pressure=None if rho is None else _sum(pressures)
    else:raise ValueError('Select a supported velocity-basis mode.')
    return dict(k_total=k_total,head_m=head,pressure_pa=pressure,
                pressure_kpa=None if pressure is None else pressure/1000,
                pressure_bar=None if pressure is None else pressure/100000,rows=row_heads)

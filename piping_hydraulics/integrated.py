"""Single-section orchestration. Existing engineering equations are delegated."""
import math
import advanced_engineering as phase1
from .pipe_capacity import pipe_capacity, nonnegative
from .pipe_geometry import positive
from .units import flow_to_si


def integrated_section(flow, flow_unit, diameter, length, density, viscosity,
                       roughness, k_total, flow_factors, *, common_k_basis=False,
                       length_contains_equivalent_fittings=False):
    q_input=nonnegative(flow,'Flow rate')
    d=positive(diameter,'INTERNAL diameter')
    length=nonnegative(length,'Straight pipe length')
    rho=positive(density,'Density')
    mu=positive(viscosity,'Dynamic viscosity')
    epsilon=nonnegative(roughness,'Absolute roughness')
    k=nonnegative(k_total,'Total K')
    if not common_k_basis:
        raise ValueError('Confirm K_total is referenced to this section’s calculated velocity and flow path.')
    if length_contains_equivalent_fittings:
        raise ValueError('Enter straight pipe length only; remove fitting equivalent lengths to avoid double counting.')
    # The approved positive-flow converter remains unchanged. For zero, validate
    # the unit/factor through that adapter, then apply the zero-flow identity.
    if q_input==0:
        flow_to_si(1.0,flow_unit,flow_factors)
        q=0.0
    else:
        q=flow_to_si(q_input,flow_unit,flow_factors)
    area=pipe_capacity(d,0).area_m2
    velocity=q/area
    if not math.isfinite(velocity) or (q>0 and velocity==0):
        raise ValueError('Velocity exceeds the supported numeric range.')
    re,regime=phase1.reynolds(rho,velocity,d,mu)
    rr=phase1.relative_roughness(epsilon,d)
    friction=phase1.friction_factor(re,epsilon,d)
    minor=phase1.minor_loss(k,velocity,rho)
    if q==0:
        major=phase1.Loss(0.0,0.0)
        total=phase1.Loss(0.0,0.0)
        method='Not applicable — no flow'
        complete=True
    elif friction['darcy'] is None:
        major=total=None
        method='Unavailable — transitional flow; no factor assigned'
        complete=False
    else:
        major,minor,total=phase1.total_loss(length,d,velocity,rho,friction['darcy'],k)
        method='Laminar 64/Re' if regime=='Laminar' else 'Colebrook–White'
        complete=True
    return dict(flow_m3_s=q,area_m2=area,velocity_m_s=velocity,reynolds=re,regime=regime,
                roughness_m=epsilon,relative_roughness=rr,friction=friction,method=method,
                major=major,minor=minor,total=total,complete=complete)

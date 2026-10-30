"""Basis-preserving duty profiles; no Streamlit or implicit electrical conversion."""
from dataclasses import dataclass,replace
import math
from piping_hydraulics.pipe_capacity import nonnegative
from piping_hydraulics.pipe_geometry import positive
from .pump_efficiency import power_to_watts
from .shaft_power import POWER_FACTORS
from .motor_power import motor_power
from .hydraulic_power import hydraulic_power
from .control_strategy import solve_constant_speed_system_for_target_flow,scale_vendor_power_curve,validate_shaft_hydraulic_basis,ShaftComparison
from .target_speed import solve_speed_for_target_flow
from .power_curve import interpolate_power

METHODS=('Constant Speed / Throttling','VSD','User-Supplied Input Power')
BASES=('Electrical Input Power','Motor Input Power','Shaft Power','Hydraulic Power','VFD Electrical Input Power')
ENERGY_LABELS={'Electrical Input Power':'Supply Electrical Energy','Motor Input Power':'Motor Electrical Energy','Shaft Power':'Shaft Mechanical Energy','Hydraulic Power':'Hydraulic Energy','VFD Electrical Input Power':'VFD Electrical Energy'}
SUPPLY_BASES=('Electrical Input Power','VFD Electrical Input Power')
ELECTRICAL_BASES=SUPPLY_BASES+('Motor Input Power',)
HOURS_WARNING='Total entered operating hours exceed 8760 h/year. Verify whether duty periods overlap or represent multiple pumps/assets.'
INVALID_POINT='No valid modeled operating solution.'

@dataclass(frozen=True)
class DutyPoint:
    name: str
    method: str
    hours: float
    target_flow_si: float | None = None
    input_power: float | None = None
    power_unit: str | None = None
    power_basis: str | None = None
    energy_basis: str | None = None
    motor_efficiency_percent: float | None = None
    vfd_efficiency_percent: float | None = None
    notes: str = ''
    input_error: str | None = None

@dataclass(frozen=True)
class DutyPointEnergyResult:
    case: str
    method: str
    target_flow_si: float | None
    hours: float | None
    speed_rpm: float | None = None
    head_m: float | None = None
    hydraulic_w: float | None = None
    shaft_w: float | None = None
    motor_w: float | None = None
    vfd_w: float | None = None
    energy_basis: str | None = None
    energy_kwh: float | None = None
    cost: float | None = None
    time_fraction_percent: float | None = None
    electrical_share_percent: float | None = None
    status: str = ''
    notes: str = ''
    speed_candidates_rpm: tuple[float,...] = ()
    applicable_w: float | None = None

@dataclass(frozen=True)
class AnnualEnergySummary:
    rows: tuple[DutyPointEnergyResult,...]
    total_hours: float
    hours_complete: bool
    energy_by_basis: tuple[tuple[str,float],...]
    cost_by_basis: tuple[tuple[str,float],...]
    comparable_supply_kwh: float | None
    comparable_supply_cost: float | None
    warning: str | None

@dataclass(frozen=True)
class ControlStrategyAnnualComparison:
    difference_kwh: float
    reduction_percent: float | None
    difference_cost: float | None


def calculate_energy(power_kw,hours):
    p=nonnegative(power_kw,'Applicable Power (kW)');h=nonnegative(hours,'Operating Hours per Year')
    result=p*h
    if not math.isfinite(result) or (p>0 and h>0 and result==0):raise ValueError('Energy exceeds the supported numeric range.')
    return result


def calculate_operating_cost(electrical_energy_kwh,tariff_per_kwh):
    e=nonnegative(electrical_energy_kwh,'Electrical energy (kWh)');t=nonnegative(tariff_per_kwh,'Electricity Cost per kWh')
    result=e*t
    if not math.isfinite(result) or (e>0 and t>0 and result==0):raise ValueError('Operating cost exceeds the supported numeric range.')
    return result


def vfd_input_power(motor_input_w,efficiency_percent):
    try:return motor_power(motor_input_w,'W',efficiency_percent).input_watts
    except ValueError as exc:raise ValueError(str(exc).replace('Motor efficiency','VFD efficiency')) from None


def _evaluate_row(row,curve,speed,system,density,power_curve,tariff):
    if row.input_error:raise ValueError(row.input_error)
    hours=nonnegative(row.hours,'Operating Hours per Year')
    if row.method not in METHODS:raise ValueError('Select a supported control method.')
    h=shaft=motor=vfd=None;n=head=None;candidates=();q=row.target_flow_si
    basis=row.energy_basis
    if row.method==METHODS[2]:
        if q is not None:nonnegative(q,'Target Flow (informational in direct mode)')
        if row.power_basis not in BASES[:4]:raise ValueError('Select the explicitly supplied power basis.')
        watts=power_to_watts(row.input_power,row.power_unit,'User-supplied power',allow_zero=True)
        basis=basis or row.power_basis
        powers={row.power_basis:watts}
        if row.power_basis=='Shaft Power':shaft=watts
        if row.power_basis=='Hydraulic Power':h=watts
        if row.power_basis=='Motor Input Power':motor=watts
        if basis in ('Motor Input Power','VFD Electrical Input Power') and row.power_basis=='Shaft Power':
            motor=motor_power(watts,'W',row.motor_efficiency_percent).input_watts;powers['Motor Input Power']=motor
        if basis=='VFD Electrical Input Power' and motor is not None:
            vfd=vfd_input_power(motor,row.vfd_efficiency_percent);powers[basis]=vfd
        if basis not in powers:raise ValueError('Selected energy basis cannot be obtained from the supplied power and explicit efficiencies.')
        applicable=powers[basis]
    else:
        q=positive(q,'Target Operating Flow')
        if curve is None or system is None:raise ValueError(INVALID_POINT+' Pump/system data are required.')
        positive(speed,'Reference Speed')
        if row.method==METHODS[0]:
            try:point=solve_constant_speed_system_for_target_flow(curve,system.static_head_m,q)
            except (ValueError,OverflowError) as exc:raise ValueError(INVALID_POINT+' '+str(exc)) from None
            n=speed;head=point.head_m
        else:
            try:result=solve_speed_for_target_flow(curve,speed,system,q)
            except (ValueError,OverflowError) as exc:raise ValueError(INVALID_POINT+' '+str(exc)) from None
            candidates=tuple(s.required_speed_rpm for s in result.solutions)
            if len(result.solutions)!=1 or result.coincident_ratio_intervals:
                raise ValueError(INVALID_POINT+' No unique VSD speed is available; all candidates require separate assessment: '+(', '.join(f'{s:.12g} rpm' for s in candidates) or 'none/continuous interval'))
            n=result.solutions[0].required_speed_rpm;head=result.target_system_head_m
        h=hydraulic_power(density=density,density_unit='kg/m³',flow=q,flow_unit='m³/s',head_m=head,
            density_factors={'kg/m³':1.0},flow_factors={'m³/s':1.0}).watts
        if basis not in BASES[1:]:raise ValueError('Choose hydraulic, shaft, motor electrical or VFD electrical energy for a modeled row.')
        if basis=='VFD Electrical Input Power' and row.method!=METHODS[1]:raise ValueError('VFD electrical energy applies only to the VSD control method.')
        if power_curve is not None:
            applicable_curve=power_curve if row.method==METHODS[0] else scale_vendor_power_curve(power_curve,speed,n)
            try:shaft=interpolate_power(applicable_curve,q).shaft_power_w
            except ValueError:
                if basis!='Hydraulic Power':raise
        if basis!='Hydraulic Power':
            if shaft is None:raise ValueError('Vendor shaft-power data are required for the selected energy basis.')
            if basis in ('Motor Input Power','VFD Electrical Input Power'):
                validate_shaft_hydraulic_basis(ShaftComparison(shaft,shaft,None,None),h,h)
                motor=motor_power(shaft,'W',row.motor_efficiency_percent).input_watts
                if basis=='VFD Electrical Input Power':vfd=vfd_input_power(motor,row.vfd_efficiency_percent)
        applicable={'Hydraulic Power':h,'Shaft Power':shaft,'Motor Input Power':motor,'VFD Electrical Input Power':vfd}[basis]
    energy=calculate_energy(applicable/POWER_FACTORS['kW'],hours)
    cost=calculate_operating_cost(energy,tariff) if tariff is not None and basis in ELECTRICAL_BASES else None
    status='Calculated from explicitly supplied data.'
    if row.method!=METHODS[2] and basis=='Shaft Power':
        try:validate_shaft_hydraulic_basis(ShaftComparison(shaft,shaft,None,None),h,h)
        except ValueError:status='Entered/scaled mechanical-energy arithmetic only: shaft power is below hydraulic power; electrical conversion is unavailable.'
    if basis=='Motor Input Power' and row.method==METHODS[1]:status+=' Motor-terminal basis excludes unspecified VFD losses; not included in comparable supply total.'
    return DutyPointEnergyResult(row.name,row.method,q,hours,n,head,h,shaft,motor,vfd,basis,energy,cost,status=status,notes=row.notes,speed_candidates_rpm=candidates,applicable_w=applicable)


def evaluate_duty_profile(rows,*,curve=None,reference_speed=None,system=None,density=None,power_curve=None,tariff=None):
    if not 1<=len(rows)<=20:raise ValueError('Enter 1 to 20 duty periods.')
    if tariff is not None:nonnegative(tariff,'Electricity Cost per kWh')
    results=[];hours_values=[];complete=True
    for row in rows:
        try:hours_values.append(nonnegative(row.hours,'Operating Hours per Year'))
        except ValueError:complete=False
        try:result=_evaluate_row(row,curve,reference_speed,system,density,power_curve,tariff)
        except (ValueError,OverflowError,ZeroDivisionError) as exc:
            try:hours=nonnegative(row.hours,'Operating Hours per Year')
            except ValueError:hours=None
            result=DutyPointEnergyResult(row.name,row.method,row.target_flow_si,hours,status=str(exc),notes=row.notes)
        results.append(result)
    total=math.fsum(hours_values)
    if not math.isfinite(total):raise ValueError('Total operating hours exceed the supported numeric range.')
    energy={};costs={}
    for basis in BASES:
        values=[r.energy_kwh for r in results if r.energy_basis==basis and r.energy_kwh is not None]
        if values:energy[basis]=math.fsum(values)
        values=[r.cost for r in results if r.energy_basis==basis and r.cost is not None]
        if values:costs[basis]=math.fsum(values)
    if any(not math.isfinite(v) for v in list(energy.values())+list(costs.values())):raise ValueError('Annual totals exceed the supported numeric range.')
    supply_values=[r.energy_kwh for r in results if r.energy_basis in SUPPLY_BASES and r.energy_kwh is not None]
    supply=math.fsum(supply_values) if supply_values else None
    supply_cost=math.fsum([r.cost for r in results if r.energy_basis in SUPPLY_BASES and r.cost is not None]) if tariff is not None and supply_values else None
    if supply is not None and not math.isfinite(supply):raise ValueError('Supply-energy total exceeds the supported numeric range.')
    results=[replace(r,time_fraction_percent=r.hours/total*100 if total>0 and r.hours is not None else None,
        electrical_share_percent=r.energy_kwh/supply*100 if supply is not None and supply>0 and r.energy_basis in SUPPLY_BASES and r.energy_kwh is not None else None) for r in results]
    return AnnualEnergySummary(tuple(results),total,complete,tuple(energy.items()),tuple(costs.items()),supply,supply_cost,HOURS_WARNING if total>8760 else None)


def compare_control_alternatives(constant,vsd):
    if constant.method!=METHODS[0] or vsd.method!=METHODS[1]:raise ValueError('Choose one constant-speed and one VSD row as alternatives.')
    if constant.energy_basis!='Motor Input Power' or vsd.energy_basis!='VFD Electrical Input Power':raise ValueError('Comparison requires constant-speed motor electrical input and VSD supply electrical input (including entered VFD losses).')
    if constant.energy_kwh is None or vsd.energy_kwh is None:raise ValueError('Both selected alternatives need valid electrical energy.')
    if not math.isclose(constant.target_flow_si,vsd.target_flow_si,rel_tol=1e-12,abs_tol=1e-14) or constant.hours!=vsd.hours:raise ValueError('Alternative rows must have the same target flow and entered hours.')
    delta=constant.energy_kwh-vsd.energy_kwh
    percent=delta/constant.energy_kwh*100 if constant.energy_kwh else None
    cost=constant.cost-vsd.cost if constant.cost is not None and vsd.cost is not None else None
    return ControlStrategyAnnualComparison(delta,percent,cost)

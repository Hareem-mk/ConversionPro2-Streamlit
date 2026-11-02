"""Traceable section-level orchestration. No independent engineering/finance equations."""
from dataclasses import dataclass
from . import (pump_curve,system_curve,operating_point,bep_operating_range,efficiency_curve,
    power_curve,npshr_curve,npsh_margin,curve_characteristics,system_sensitivity,
    variable_speed,target_speed,control_strategy,annual_energy,economic_sensitivity,
    monte_carlo_economics)
from .pump_efficiency import power_to_watts
from piping_hydraulics.npsha import NPSHAvailable
from piping_hydraulics.pipe_geometry import positive

MODES=('Technical Review','Technical + Energy Review','Technical + Economic Review','Full Integrated Review')
AVAILABLE='Data Available'
NOT_EVALUATED='Not Evaluated'
OUTSIDE='Outside Supplied Curve Range'

@dataclass(frozen=True)
class CurveInput:
    points: tuple
    flow_unit: str | None
    ordinate_unit: str | None = None
    error: str | None = None

@dataclass(frozen=True)
class SystemInput:
    static_head: float | None
    head_unit: str | None
    method: str = 'Reference Flow / Friction Head'
    reference_flow: float | None = None
    reference_friction_head: float | None = None
    flow_unit: str | None = None
    k_si: float | None = None

@dataclass(frozen=True)
class TechnicalInputs:
    pump: CurveInput | None
    system: SystemInput | None
    bep_flow: float | None = None
    bep_unit: str | None = None
    efficiency: CurveInput | None = None
    power: CurveInput | None = None
    npshr: CurveInput | None = None
    npsha: float | NPSHAvailable | None = None
    npsha_unit: str | None = None
    driver_rating: float | None = None
    driver_unit: str | None = None
    selected_intersection: int | None = None
    reference_speed: float | None = None
    new_speed: float | None = None
    target_flow: float | None = None
    target_unit: str | None = None
    control_requested: bool = False
    density_kg_m3: float | None = None
    modified_system: SystemInput | None = None
    required_npsh_margin_m: float | None = None
    required_driver_margin_percent: float | None = None
    minimum_speed: float | None = None
    maximum_speed: float | None = None

@dataclass(frozen=True)
class EnergyInputs:
    rows: tuple
    tariff: float | None = None

@dataclass(frozen=True)
class SensitivityInputs:
    variable: str
    values: tuple
    percentage: bool = False

@dataclass(frozen=True)
class RiskInputs:
    distributions: tuple
    trials: int
    seed: int | None = None
    cost_basis: str = monte_carlo_economics.DIRECT_COSTS

@dataclass(frozen=True)
class ResultTraceabilityItem:
    section: str
    metric: str
    value: float | str | None
    unit: str
    source: str
    status: str
    note: str = ''

@dataclass(frozen=True)
class ReviewFlag:
    section: str
    message: str

@dataclass(frozen=True)
class DataCompletenessItem:
    dataset: str
    status: str

@dataclass(frozen=True)
class TechnicalSummary:
    pump: object | None
    system: object | None
    operating_points: object | None
    selected_point: object | None
    efficiency_curve: object | None
    power_curve: object | None
    npshr_curve: object | None
    characteristics: object | None
    system_sensitivity: object | None
    variable_speed: object | None
    target_speed: object | None
    control_strategy: object | None

@dataclass(frozen=True)
class IntegratedPumpSummary:
    mode: str
    identification: tuple
    items: tuple[ResultTraceabilityItem,...]
    flags: tuple[ReviewFlag,...]
    completeness: tuple[DataCompletenessItem,...]
    assumptions: tuple[str,...]
    technical: TechnicalSummary
    energy: object | None
    economic: object | None
    sensitivity: object | None
    break_even_capex: object | None
    risk: object | None

    def metric(self,name):
        return next(row for row in self.items if row.metric==name)


def parse_curve_text(text,flow_unit,ordinate_unit):
    if not text.strip():return None
    points=[]
    for index,line in enumerate(text.splitlines(),1):
        if not line.strip():continue
        pair=[part.strip() for part in line.split(',')]
        if len(pair)!=2 or not all(pair):return CurveInput((),flow_unit,ordinate_unit,f'Line {index}: enter flow, value without thousands separators.')
        points.append(tuple(pair))
    return CurveInput(tuple(points),flow_unit,ordinate_unit)


def build_system(data,flow_factors):
    if data is None:raise ValueError('System curve was not supplied.')
    if data.method=='Direct K':return system_curve.model_from_k(data.static_head,data.head_unit,data.k_si)
    if data.method!='Reference Flow / Friction Head':raise ValueError('Select a supported system method.')
    return system_curve.model_from_reference(static_head=data.static_head,head_unit=data.head_unit,
        reference_flow=data.reference_flow,reference_friction_head=data.reference_friction_head,
        flow_unit=data.flow_unit,flow_factors=flow_factors)


def build_integrated_pump_summary(technical_inputs,flow_factors,*,mode=MODES[0],identification=(),
        optional_energy_inputs=None,optional_economic_inputs=None,optional_sensitivity_inputs=None,
        optional_risk_inputs=None):
    if mode not in MODES:raise ValueError('Select a supported integrated review mode.')
    data=technical_inputs;items=[];flags=[];assumptions=[]
    def add(section,name,value,unit,source,status=None,note=''):
        items.append(ResultTraceabilityItem(section,name,value,unit,source,status or (AVAILABLE if value is not None else NOT_EVALUATED),note))
    def attempt(section,func):
        try:return func()
        except (ValueError,OverflowError) as error:
            flags.append(ReviewFlag(section,str(error)));return None
    def dataset(curve,func):
        if curve.error:raise ValueError(curve.error)
        return func()
    pump=attempt('Hydraulics',lambda:dataset(data.pump,lambda:pump_curve.create_pump_curve(data.pump.points,data.pump.flow_unit,data.pump.ordinate_unit,flow_factors))) if data.pump is not None else None
    model=attempt('Hydraulics',lambda:build_system(data.system,flow_factors)) if data.system is not None else None
    eff=attempt('Pump Performance',lambda:dataset(data.efficiency,lambda:efficiency_curve.create_efficiency_curve(data.efficiency.points,data.efficiency.flow_unit,flow_factors))) if data.efficiency else None
    power=attempt('Pump Performance',lambda:dataset(data.power,lambda:power_curve.create_power_curve(data.power.points,data.power.flow_unit,data.power.ordinate_unit,flow_factors))) if data.power else None
    npshr=attempt('NPSH',lambda:dataset(data.npshr,lambda:npshr_curve.create_npshr_curve(data.npshr.points,data.npshr.flow_unit,data.npshr.ordinate_unit,flow_factors))) if data.npshr else None
    roots=attempt('Hydraulics',lambda:operating_point.find_operating_points(pump,model)) if pump and model else None
    point=None
    if roots is not None:
        if data.selected_intersection is not None:
            index=data.selected_intersection
            if isinstance(index,bool) or not isinstance(index,int) or not 0<=index<len(roots.points):flags.append(ReviewFlag('Hydraulics','Entered intersection index is not a valid isolated operating point.'))
            else:point=roots.points[index]
        elif len(roots.points)==1 and not roots.coincident_intervals:point=roots.points[0]
        if len(roots.points)>1 or roots.coincident_intervals:flags.append(ReviewFlag('Hydraulics','Multiple Valid Intersections: all isolated points and coincident intervals are shown. Select an isolated point explicitly for downstream vendor review.'))
        elif not roots.points:flags.append(ReviewFlag('Hydraulics',operating_point.NO_INTERSECTION))
    if point is None:flags.append(ReviewFlag('Pump Performance','No unique or explicitly selected operating point; flow-dependent vendor results are Not Evaluated.'))
    for name,value,unit in [('Operating Flow',point.flow_m3_s if point else None,'m³/s'),('Operating Head',point.head_m if point else None,'m'),('Pump Head',point.pump_head_m if point else None,'m'),('System Head',point.system_head_m if point else None,'m'),('Pump/System Residual',point.residual_m if point else None,'m'),('Valid Isolated Intersections',len(roots.points) if roots else None,'count')]:add('Hydraulics',name,value,unit,'Phase 3G')
    add('Hydraulics','Operating Point Selection',('Explicit intersection index '+str(data.selected_intersection) if data.selected_intersection is not None else 'Unique isolated intersection (index 0)') if point else None,'','Phase 3G / User Selection')
    add('Hydraulics','Static Head',model.static_head_m if model else None,'m','Phase 3F')
    add('Hydraulics','System Resistance',model.k_si if model else None,'s²/m⁵','Phase 3F')
    if pump:assumptions.extend(['Single-phase incompressible hydraulic assumptions apply to the pump/system model.','User-supplied vendor curves must match the relevant pump configuration, speed and impeller diameter.','Supplied pump and vendor performance curves use the existing bounded linear-interpolation kernels; no extrapolation is performed.'])
    def point_metric(section,name,unit,source,provided,func):
        before=len(flags);result=attempt(section,func) if point is not None and provided else None
        status=OUTSIDE if len(flags)>before and 'outside' in flags[-1].message.lower() and 'range' in flags[-1].message.lower() else None
        add(section,name,result,unit,source,status)
        return result
    bep=point_metric('Pump Performance','Percent of BEP','%','Phase 3H',data.bep_flow is not None,
        lambda:bep_operating_range.compare_bep(point.flow_m3_s,pump_curve.curve_flow_to_si(data.bep_flow,data.bep_unit,flow_factors)).percent_bep)
    if data.bep_flow is None:flags.append(ReviewFlag('Pump Performance','Vendor BEP not entered; BEP is not inferred from efficiency peak.'))
    point_metric('Pump Performance','Operating Efficiency','%','Phase 3M',eff is not None,lambda:efficiency_curve.interpolate_efficiency(eff,point.flow_m3_s).efficiency_percent)
    shaft=point_metric('Pump Performance','Pump Shaft Power','W','Phase 3N',power is not None,lambda:power_curve.interpolate_power(power,point.flow_m3_s).shaft_power_w)
    driver=attempt('Pump Performance',lambda:power_curve.calculate_driver_margin(shaft,power_to_watts(data.driver_rating,data.driver_unit,'Driver Rating',allow_zero=False))) if shaft is not None and data.driver_rating is not None else None
    add('Pump Performance','Driver Power Margin',driver.margin_w if driver else None,'W','Phase 3N')
    add('Pump Performance','Driver Power Margin Percent',driver.margin_percent if driver else None,'%','Phase 3N',note=driver.relationship_status if driver else '')
    driver_status=attempt('Criteria',lambda:power_curve.compare_driver_margin(driver.margin_percent,data.required_driver_margin_percent)) if driver and data.required_driver_margin_percent is not None else None
    add('Criteria','Entered Driver Margin Criterion',driver_status,'','Phase 3N',None if data.required_driver_margin_percent is not None else 'Criterion Not Entered')
    if data.driver_rating is None:flags.append(ReviewFlag('Pump Performance','Driver rating not entered.'))
    required=point_metric('NPSH','Vendor NPSHR','m','Phase 3O',npshr is not None,lambda:npshr_curve.interpolate_npshr(npshr,point.flow_m3_s).npshr_m)
    available=attempt('NPSH',lambda:data.npsha.total_npsha_m if isinstance(data.npsha,NPSHAvailable) else system_curve.head_to_metres(data.npsha,data.npsha_unit,'NPSHA')) if data.npsha is not None else None
    if isinstance(data.npsha,NPSHAvailable):
        for warning in data.npsha.warnings:flags.append(ReviewFlag('NPSH',warning))
    add('NPSH','NPSHA',available,'m','Phase 2H' if isinstance(data.npsha,NPSHAvailable) else 'User Input / Phase 3J')
    margin=attempt('NPSH',lambda:npsh_margin.margin_from_phase2h(data.npsha,required) if isinstance(data.npsha,NPSHAvailable) else npsh_margin.calculate_npsh_margin(available,required)) if required is not None and available is not None else None
    for name,value,unit in [('NPSH Margin',margin.margin_m if margin else None,'m'),('NPSHA / NPSHR Ratio',margin.ratio if margin else None,''),('NPSH Percent Margin',margin.percent_margin if margin else None,'%'),('NPSH Relationship',margin.relationship_status if margin else None,'')]:add('NPSH',name,value,unit,'Phase 3J')
    criterion=attempt('Criteria',lambda:npsh_margin.compare_required_margin(margin.margin_m,data.required_npsh_margin_m).criterion_status) if margin and data.required_npsh_margin_m is not None else None
    add('Criteria','Entered NPSH Margin Criterion',criterion,'','Phase 3J',None if data.required_npsh_margin_m is not None else 'Criterion Not Entered')
    if npshr is not None or data.npsha is not None:assumptions.append('NPSHR must be applicable vendor data at the selected flow; positive margin alone does not establish all project reliability/cavitation criteria.')
    chars=attempt('Curve Characteristics',lambda:curve_characteristics.analyze_curve_characteristics(pump)) if pump else None
    for name,value,unit in [('Supplied Shutoff Head',chars.shutoff_head_m if chars else None,'m'),('Maximum Supplied Flow',chars.maximum_flow_m3_s if chars else None,'m³/s'),('Head at Maximum Supplied Flow',chars.maximum_flow_point.head_m if chars else None,'m'),('Monotonicity',chars.monotonicity_status if chars else None,''),('Flat Segment Count',chars.flat_segment_count if chars else None,'count'),('Rising Segment Count',chars.rising_segment_count if chars else None,'count')]:add('Curve Characteristics',name,value,unit,'Phase 3Q')
    slope=attempt('Curve Characteristics',lambda:curve_characteristics.local_curve_slope(pump,point.flow_m3_s)) if pump and point else None
    if slope:
        for i,segment in enumerate(slope.local_segments):add('Curve Characteristics','Local Pump Curve Slope'+(f' {i+1}' if len(slope.local_segments)>1 else ''),segment.slope_si,'m per (m³/s)','Phase 3Q',note=f'Supplied segment {segment.index}; no stability classification.')
    else:add('Curve Characteristics','Local Pump Curve Slope',None,'m per (m³/s)','Phase 3Q')
    rise=attempt('Curve Characteristics',lambda:curve_characteristics.calculate_shutoff_head_rise(chars.shutoff_head_m,point.head_m)) if chars and chars.shutoff_head_m is not None and point else None
    add('Curve Characteristics','Head Rise to Shutoff',rise.rise_m if rise else None,'m','Phase 3Q')
    changed=attempt('System Sensitivity',lambda:system_sensitivity.evaluate_system_sensitivity(pump,model,build_system(data.modified_system,flow_factors))) if pump and model and data.modified_system else None
    add('System Sensitivity','Operating Flow Shift',changed.flow_change.difference if changed and changed.flow_change else None,'m³/s','Phase 3R')
    add('System Sensitivity','Operating Head Shift',changed.head_change.difference if changed and changed.head_change else None,'m','Phase 3R')
    reference=attempt('Variable Speed',lambda:positive(data.reference_speed,'Reference Speed')) if data.reference_speed is not None else None
    add('Variable Speed','Reference Speed',reference,'rpm','User Input')
    vsd=attempt('Variable Speed',lambda:variable_speed.evaluate_variable_speed_operating_point(pump,data.reference_speed,data.new_speed,model)) if pump and model and data.new_speed is not None else None
    vp=vsd.new.points[0] if vsd and len(vsd.new.points)==1 and not vsd.new.coincident_intervals else None
    add('Variable Speed','VSD Operating Flow',vp.flow_m3_s if vp else None,'m³/s','Phase 3S');add('Variable Speed','VSD Operating Head',vp.head_m if vp else None,'m','Phase 3S')
    add('Variable Speed','New Speed',vsd.scaling.new_speed_rpm if vsd else None,'rpm','Phase 3S');add('Variable Speed','Speed Ratio',vsd.scaling.ratio if vsd else None,'','Phase 3S')
    if vsd and vp is None:flags.append(ReviewFlag('Variable Speed','VSD has no unique isolated operating point; all returned intersections are listed.'))
    target=attempt('Target Speed',lambda:target_speed.solve_speed_for_target_flow(pump,data.reference_speed,model,pump_curve.curve_flow_to_si(data.target_flow,data.target_unit,flow_factors))) if pump and model and data.target_flow is not None else None
    solution=target.solutions[0] if target and len(target.solutions)==1 and not target.coincident_ratio_intervals else None
    for name,value,unit in [('Required Speed',solution.required_speed_rpm if solution else None,'rpm'),('Target Flow',target.target_flow_m3_s if target else None,'m³/s'),('Verified Target Head',solution.verified_head_m if solution else None,'m')]:add('Target Speed',name,value,unit,'Phase 3T')
    if target and solution is None:flags.append(ReviewFlag('Target Speed','No unique required-speed solution; all solutions and coincident ratio intervals are listed.'))
    limit=attempt('Criteria',lambda:target_speed.compare_speed_limits(solution.required_speed_rpm,data.minimum_speed,data.maximum_speed)) if solution and (data.minimum_speed is not None or data.maximum_speed is not None) else None
    add('Criteria','Entered Speed Criterion',limit,'','Phase 3T',None if data.minimum_speed is not None or data.maximum_speed is not None else 'Criterion Not Entered')
    control=attempt('Control Strategy',lambda:control_strategy.compare_throttling_and_vsd(pump,data.reference_speed,model,pump_curve.curve_flow_to_si(data.target_flow,data.target_unit,flow_factors),data.density_kg_m3)) if pump and model and data.control_requested else None
    for name,value,unit in [('Throttling Head',control.constant_speed.head_m if control and control.constant_speed else None,'m'),('Required Throttled K',control.constant_speed.system.k_si if control and control.constant_speed else None,'s²/m⁵'),('Resistance Increase',control.resistance_change.percent if control and control.resistance_change else None,'%')]:add('Control Strategy',name,value,unit,'Phase 3U')
    reduction=attempt('Control Strategy',lambda:control_strategy.difference_relative_to_first(control.constant_hydraulic_w,control.vsd_hydraulic_w[0]).percent) if control and control.constant_hydraulic_w is not None and len(control.vsd_hydraulic_w)==1 and control.vsd is not None and not control.vsd.coincident_ratio_intervals else None
    add('Control Strategy','Hydraulic Power Reduction',reduction,'%','Phase 3U',note='Hydraulic power reduction is not electrical-energy saving.')
    if control:
        for error in (control.constant_speed_error,control.vsd_error):
            if error:flags.append(ReviewFlag('Control Strategy',error))
    if vsd or target or control:assumptions.extend(['Affinity-law speed-scaled head curves and required speeds are theoretical estimates requiring vendor verification.','NPSHR is not automatically scaled with speed. Base-flow vendor efficiency, shaft power and NPSHR results are not presented as new-speed vendor predictions.','Hydraulic power, shaft power, motor input and supply electrical energy are distinct boundaries.'])
    energy_mode=mode in (MODES[1],MODES[3]);econ_mode=mode in (MODES[2],MODES[3])
    energy=attempt('Energy',lambda:annual_energy.evaluate_duty_profile(optional_energy_inputs.rows,tariff=optional_energy_inputs.tariff)) if energy_mode and optional_energy_inputs else None
    add('Energy','Annual Supply Electrical Energy',energy.comparable_supply_kwh if energy else None,'kWh/year','Phase 3V')
    add('Energy','Annual Supply Electrical Operating Cost',energy.comparable_supply_cost if energy else None,'currency/year','Phase 3V')
    if energy:
        invalid=[r for r in energy.rows if r.energy_kwh is None]
        if invalid:flags.append(ReviewFlag('Energy',f'{len(invalid)} duty rows were not evaluated; displayed totals are partial accepted Phase 3V totals.'))
        if energy.warning:flags.append(ReviewFlag('Energy',energy.warning))
        assumptions.append('Annual energy uses entered duty powers/hours and explicitly selected bases; mechanical/hydraulic totals are not mixed into comparable supply electrical energy or tariff cost.')
    econ=attempt('Economics',lambda:economic_sensitivity.evaluate_economic_scenario(optional_economic_inputs).result) if econ_mode and optional_economic_inputs else None
    for name,value,unit in [('Annual Operating Cost Difference',econ.annual_cost_difference if econ else None,'currency/year'),('Incremental CAPEX',econ.incremental_capex if econ else None,'currency'),('Simple Payback',econ.simple_payback_years if econ else None,'years'),('NPV',econ.npv if econ else None,'currency'),('Lifecycle Cost Difference',econ.lifecycle_cost_difference if econ else None,'currency'),('Baseline Lifecycle Cost',econ.baseline.lifecycle_cost if econ else None,'currency'),('Proposed Lifecycle Cost',econ.proposed.lifecycle_cost if econ else None,'currency')]:add('Economics',name,value,unit,'Phase 3W')
    if econ:assumptions.append('Economics use entered assumptions and unchanged Phase 3W end-of-year cash flows; simple payback excludes optional maintenance, escalation and residuals, while NPV includes them. Currency is a label only.')
    sensitivity=attempt('Economic Sensitivity',lambda:economic_sensitivity.run_one_variable_sensitivity(optional_economic_inputs,optional_sensitivity_inputs.variable,optional_sensitivity_inputs.values,percentage=optional_sensitivity_inputs.percentage)) if econ and optional_sensitivity_inputs else None
    breakeven=attempt('Economic Sensitivity',lambda:economic_sensitivity.calculate_break_even_capex(optional_economic_inputs)) if sensitivity else None
    add('Economic Sensitivity','Break-Even Incremental CAPEX',breakeven.value if breakeven else None,'currency','Phase 3X')
    if econ_mode and not sensitivity:flags.append(ReviewFlag('Economic Sensitivity','Economic sensitivity not evaluated.'))
    risk=attempt('Probabilistic Risk',lambda:monte_carlo_economics.run_economic_monte_carlo(optional_economic_inputs,dict(optional_risk_inputs.distributions),optional_risk_inputs.trials,optional_risk_inputs.seed,cost_basis=optional_risk_inputs.cost_basis)) if econ and optional_risk_inputs else None
    risk_summary=risk.summary if risk else None
    for name,value,unit in [('Mean NPV',risk_summary.npv.mean if risk_summary else None,'currency'),('Median NPV',risk_summary.npv.median if risk_summary else None,'currency')]:add('Probabilistic Risk',name,value,unit,'Phase 3Y')
    percentiles=dict(risk_summary.npv.percentiles) if risk_summary else {}
    for p in (10,50,90):add('Probabilistic Risk',f'P{p} NPV',percentiles.get(p),'currency','Phase 3Y')
    add('Probabilistic Risk','Probability NPV > 0',risk_summary.probability_positive_npv_percent if risk_summary else None,'%','Phase 3Y')
    if risk:
        if risk.warning:flags.append(ReviewFlag('Probabilistic Risk',risk.warning))
        assumptions.append('Monte Carlo probabilities are conditional on explicitly entered distributions and valid trials. Phase 3Y assumes uncertain inputs are statistically independent; no investment decision is inferred.')
    elif econ_mode:flags.append(ReviewFlag('Probabilistic Risk','Monte Carlo simulation not run; no probability claims are introduced.'))
    for name,present in [('Efficiency Curve',data.efficiency is not None),('Power Curve',data.power is not None),('NPSHR Curve',data.npshr is not None)]:
        if not present:flags.append(ReviewFlag('Data',name+' not supplied; section Not Evaluated.'))
    completeness=[]
    for name,present,relevant in [('Pump Head Curve',data.pump is not None,True),('System Curve',data.system is not None,True),('BEP',data.bep_flow is not None,True),('Efficiency Curve',data.efficiency is not None,True),('Power Curve',data.power is not None,True),('NPSHR Curve',data.npshr is not None,True),('NPSHA',data.npsha is not None,True),('Driver Rating',data.driver_rating is not None,True),('Energy Profile',optional_energy_inputs is not None,energy_mode),('Economic Inputs',optional_economic_inputs is not None,econ_mode),('Sensitivity Inputs',optional_sensitivity_inputs is not None,econ_mode),('Monte Carlo Inputs',optional_risk_inputs is not None,econ_mode)]:
        completeness.append(DataCompletenessItem(name,'Not Required for Selected Mode' if not relevant else ('Available' if present else 'Not Supplied')))
    assumptions.append('This review consolidates supplied data and module results; no overall engineering, safety or investment approval or score is produced.')
    technical=TechnicalSummary(pump,model,roots,point,eff,power,npshr,chars,changed,vsd,target,control)
    return IntegratedPumpSummary(mode,tuple(identification),tuple(items),tuple(flags),tuple(completeness),tuple(assumptions),technical,energy,econ,sensitivity,breakeven,risk)

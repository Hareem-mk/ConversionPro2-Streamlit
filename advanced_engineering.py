"""Phase 1: SI calculations for steady, incompressible Newtonian pipe flow."""
import math
from dataclasses import dataclass

G = 9.80665
SJ_RANGE = '5,000 ≤ Re ≤ 10⁸ and 10⁻⁶ ≤ ε/D ≤ 10⁻²'
EXCLUSIONS = ('Major + minor frictional pressure loss only. Excludes static elevation head, '
              'equipment pressure losses, pump/compressor head, and other system effects.')


def value(x, name, positive=False):
    if x is None or isinstance(x, bool):
        raise ValueError(f'{name} is required and must be numeric.')
    try:
        x = float(x)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be numeric.') from None
    if not math.isfinite(x) or x < 0 or (positive and x == 0):
        raise ValueError(f'{name} must be finite and {"greater than zero" if positive else "nonnegative"}.')
    return x


def checked(x):
    if not math.isfinite(x):
        raise ValueError('Calculation exceeds the supported numeric range.')
    return x


def regime(re):
    re = value(re, 'Reynolds number')
    return 'No flow' if re == 0 else 'Laminar' if re < 2300 else 'Transitional' if re < 4000 else 'Turbulent'


def reynolds(density, velocity, diameter, viscosity):
    rho = value(density, 'Density', True)
    v = value(velocity, 'Velocity')
    d = value(diameter, 'Internal diameter', True)
    mu = value(viscosity, 'Dynamic viscosity', True)
    re = checked(rho * v * d / mu)
    if v > 0 and re == 0:
        raise ValueError('Reynolds number underflow; rescale inputs.')
    return re, regime(re)


def relative_roughness(roughness, diameter):
    rr = checked(value(roughness, 'Absolute roughness') / value(diameter, 'Internal diameter', True))
    if rr > 0.05:
        raise ValueError('This calculator supports relative roughness ε/D ≤ 0.05.')
    return rr


def colebrook_residual(f, re, rr):
    return 1 / math.sqrt(f) + 2 * math.log10(rr / 3.7 + 2.51 / (re * math.sqrt(f)))


@dataclass(frozen=True)
class ColebrookResult:
    factor: float
    residual: float
    iterations: int


def colebrook(re, roughness, diameter, *, max_iterations=200):
    re = value(re, 'Reynolds number', True)
    rr = relative_roughness(roughness, diameter)
    if re < 4000:
        raise ValueError('Colebrook–White requires turbulent flow: Re ≥ 4,000.')
    if not isinstance(max_iterations, int) or max_iterations < 1:
        raise ValueError('Iteration limit must be a positive integer.')
    # Solve for x = 1/sqrt(f). Residual is monotone increasing in x.
    # Lower endpoint is safely negative for Re >= 4000, rr <= .05.
    lo, hi = 1e-12, 1024.0
    def residual_x(x):
        return x + 2 * math.log10(rr / 3.7 + (2.51 * x) / re)
    if not residual_x(lo) < 0 < residual_x(hi):
        raise ValueError('Could not bracket the Colebrook root.')
    for iteration in range(1, max_iterations + 1):
        x = (lo + hi) / 2
        residual = residual_x(x)
        if residual > 0:
            hi = x
        else:
            lo = x
        if hi - lo <= 1e-12 * max(1.0, abs(x)) and abs(residual) <= 1e-10:
            factor = checked(1 / (x*x))
            final_residual = checked(colebrook_residual(factor, re, rr))
            if abs(final_residual) > 1e-10:
                raise ValueError('Colebrook final equation residual failed verification.')
            return ColebrookResult(factor, final_residual, iteration)
    raise ValueError('Colebrook solver did not converge; no friction factor accepted.')


def swamee_jain(re, roughness, diameter):
    re = value(re, 'Reynolds number', True)
    rr = relative_roughness(roughness, diameter)
    if not (5000 <= re <= 1e8 and 1e-6 <= rr <= 1e-2):
        raise ValueError('Swamee–Jain not calculated: outside applicability range ' + SJ_RANGE + '.')
    return checked(0.25 / math.log10(rr / 3.7 + 5.74 / re**0.9)**2)


def friction_factor(re, roughness, diameter):
    re = value(re, 'Reynolds number')
    rr = relative_roughness(roughness, diameter)
    flow = regime(re)
    result = dict(regime=flow, relative_roughness=rr, darcy=None, swamee_jain=None,
                  comparison_percent=None, residual=None, iterations=None, note='')
    if re == 0:
        result['note'] = 'No flow: Darcy friction factor is undefined at Re = 0.'
    elif re < 2300:
        result['darcy'] = checked(64 / re)
        result['note'] = 'Laminar: f = 64/Re. Swamee–Jain is not applicable.'
    elif re < 4000:
        result['note'] = 'Transitional flow: no reliable friction factor assigned by these correlations.'
    else:
        cw = colebrook(re, roughness, diameter)
        result.update(darcy=cw.factor, residual=cw.residual, iterations=cw.iterations)
        if 5000 <= re <= 1e8 and 1e-6 <= rr <= 1e-2:
            sj = swamee_jain(re, roughness, diameter)
            result.update(swamee_jain=sj, comparison_percent=100 * (sj-cw.factor)/cw.factor)
        else:
            result['note'] = 'Swamee–Jain withheld: outside applicability range ' + SJ_RANGE + '.'
    return result


@dataclass(frozen=True)
class Loss:
    head_m: float
    pressure_pa: float

    @property
    def pressure_kpa(self):
        return self.pressure_pa / 1000

    @property
    def pressure_bar(self):
        return self.pressure_pa / 100000


def _loss(coefficient, velocity, density):
    # Inputs are validated before zero-flow/zero-coefficient shortcuts.
    v = value(velocity, 'Velocity')
    rho = value(density, 'Density', True)
    if coefficient == 0 or v == 0:
        return Loss(0.0, 0.0)
    try:
        head = checked(coefficient * (v*v) / (2*G))
        pressure = checked(rho * G * head)
    except OverflowError:
        raise ValueError('Calculation exceeds the supported numeric range.') from None
    if head == 0 or pressure == 0:
        raise ValueError('Loss underflow; rescale inputs.')
    return Loss(head, pressure)


def major_loss(length, diameter, velocity, density, darcy):
    length = value(length, 'Pipe length')
    diameter = value(diameter, 'Internal diameter', True)
    darcy = value(darcy, 'Darcy friction factor', True)
    return _loss(checked(darcy * (length / diameter)), velocity, density)


def minor_loss(k_total, velocity, density):
    return _loss(value(k_total, 'Total K-factor'), velocity, density)


def total_loss(length, diameter, velocity, density, darcy, k_total):
    major = major_loss(length, diameter, velocity, density, darcy)
    minor = minor_loss(k_total, velocity, density)
    total = Loss(checked(major.head_m + minor.head_m), checked(major.pressure_pa + minor.pressure_pa))
    return major, minor, total


def render():
    import streamlit as st
    st.subheader('Advanced Engineering — Phase 1')
    st.write('Steady, single-phase, incompressible Newtonian flow in a full circular pipe; '
             'friction-factor correlations assume fully developed flow. SI units throughout. '
             'Density and viscosity must correspond to the operating conditions.')
    st.caption('g = 9.80665 m/s². All factors f are Darcy factors, not Fanning factors: f_D = 4f_F.')
    st.caption('Flow limits: Re = 0: no flow; 0 < Re < 2,300: laminar; '
               '2,300 ≤ Re < 4,000: transitional; Re ≥ 4,000: turbulent.')
    fields = {
        'density': 'Density ρ (kg/m³)', 'velocity': 'Mean velocity V (m/s)',
        'diameter': 'Internal pipe diameter D (m)', 'viscosity': 'Dynamic viscosity μ (Pa·s)',
        're': 'Reynolds number Re (dimensionless)', 'roughness': 'Absolute roughness ε (m)',
        'length': 'Pipe length L (m)', 'darcy': 'Darcy friction factor f (dimensionless)',
        'k_total': 'Total K-factor (dimensionless)',
    }
    panels = [
        ('reynolds', 'Reynolds Number', ['density','velocity','diameter','viscosity'], r'Re=\frac{\rho VD}{\mu}'),
        ('friction', 'Darcy Friction Factor', ['re','roughness','diameter'], r'f_{laminar}=\frac{64}{Re}'),
        ('major', 'Darcy–Weisbach Pressure Drop', ['length','diameter','velocity','density','darcy'], r'h_f=f\frac{L}{D}\frac{V^2}{2g},\quad\Delta P_f=\rho g h_f'),
        ('minor', 'Minor Losses', ['k_total','velocity','density'], r'h_m=K\frac{V^2}{2g},\quad\Delta P_m=\rho g h_m'),
        ('total', 'Total Pressure Drop', ['length','diameter','velocity','density','darcy','k_total'], r'h_{total}=h_f+h_m,\quad\Delta P_{total}=\Delta P_f+\Delta P_m'),
    ]
    def show_loss(label, loss):
        st.write(f'**{label}**')
        st.text(f'Head loss: {loss.head_m:.10g} m\nPressure loss: {loss.pressure_pa:.10g} Pa | '
                f'{loss.pressure_kpa:.10g} kPa | {loss.pressure_bar:.10g} bar')
    for key, title, names, equation in panels:
        with st.expander(title, expanded=key == 'reynolds'):
            st.latex(equation)
            if key == 'friction':
                st.latex(r'\frac{1}{\sqrt{f}}=-2\log_{10}\left(\frac{\varepsilon}{3.7D}+\frac{2.51}{Re\sqrt{f}}\right)')
                st.latex(r'f_{SJ}=\frac{0.25}{[\log_{10}(\varepsilon/(3.7D)+5.74/Re^{0.9})]^2}')
                st.caption('Colebrook–White: Re ≥ 4,000; calculator restricts 0 ≤ ε/D ≤ 0.05. '
                           'No factor is assigned in transition. Swamee–Jain comparison only within: ' + SJ_RANGE + '.')
                st.caption('Colebrook acceptance: bracket width ≤ 10⁻¹² max(1, 1/√f), '
                           'and absolute final equation residual ≤ 10⁻¹⁰; at most 200 iterations.')
            if key in ('major','total'):
                st.caption('Enter a positive Darcy factor appropriate to this pipe and flow regime; '
                           'this panel does not infer or validate it from fluid viscosity.')
            if key in ('minor','total'):
                st.caption('K must reference the entered velocity. Explicit K = 0 means no included minor losses. '
                           'Use a common diameter/velocity basis; convert K values before combining differing sections.')
            if key == 'total':
                st.info(EXCLUSIONS)
            with st.form('adv_' + key + '_form'):
                inputs = {name: st.number_input(fields[name], value=None, min_value=0.0,
                          format='%.10g', key='adv_' + key + '_' + name) for name in names}
                submitted = st.form_submit_button('Calculate', key='adv_' + key + '_calculate')
            if submitted:
                try:
                    if key == 'reynolds':
                        re, flow = reynolds(**inputs)
                        st.text(f'Reynolds number: {re:.10g}\nFlow regime: {flow}')
                    elif key == 'friction':
                        result = friction_factor(**inputs)
                        st.text(f"Flow regime: {result['regime']}\nRelative roughness ε/D: {result['relative_roughness']:.10g}")
                        if result['darcy'] is not None:
                            st.text(f"Darcy friction factor: {result['darcy']:.10g}")
                        if result['residual'] is not None:
                            st.caption(f"Colebrook converged in {result['iterations']} iterations; verified final residual = {result['residual']:.3e}.")
                        if result['swamee_jain'] is not None:
                            st.text(f"Swamee–Jain Darcy factor: {result['swamee_jain']:.10g}\nDifference from Colebrook: {result['comparison_percent']:+.6g}%")
                        if result['note']:
                            st.warning(result['note'])
                    elif key == 'major':
                        show_loss('Major frictional loss', major_loss(**inputs))
                    elif key == 'minor':
                        show_loss('Minor frictional loss', minor_loss(**inputs))
                    else:
                        major, minor, total = total_loss(**inputs)
                        show_loss('Major frictional loss', major)
                        show_loss('Minor frictional loss', minor)
                        show_loss('Total major + minor frictional pressure loss', total)
                        st.caption(EXCLUSIONS)
                except (ValueError, OverflowError, ZeroDivisionError) as exc:
                    st.error(str(exc))

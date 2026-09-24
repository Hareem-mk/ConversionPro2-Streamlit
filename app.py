import math

TEMP = ["Celsius (°C)", "Fahrenheit (°F)", "Kelvin (K)", "Rankine (°R)"]
PRESSURE = {
    "Pascal (Pa)": 1,
    "Kilopascal (kPa)": 1000,
    "Megapascal (MPa)": 1e6,
    "Bar": 1e5,
    "Atmosphere (atm)": 101325,
    "kg/cm²": 98066.5,
    "psi (lb/in²)": 6894.757293168,
    "inHg (inch Mercury)": 3386.389,
    "mmHg (mm Mercury)": 133.322387415,
    "mmH2O (mm Water)": 9.80665,
    "Torr": 133.322368421,
}
VOLUME = {
    "Cubic meter (m³)": 1,
    "Liter (L)": 0.001,
    "Milliliter (mL)": 1e-6,
    "Microliter (µL)": 1e-9,
    "Fluid ounce (US fl oz)": 2.95735295625e-5,
    "Cup (US)": 2.365882365e-4,
    "Pint (US)": 4.73176473e-4,
    "Quart (US)": 9.46352946e-4,
    "Gallon (US)": 0.003785411784,
    "Gallon (UK)": 0.00454609,
    "Cubic foot (ft³)": 0.028316846592,
    "Cubic inch (in³)": 1.6387064e-5,
    "Barrel (bbl, US oil)": 0.158987294928,
}
MASS = {
    "Kilogram (kg)": 1,
    "Gram (g)": 0.001,
    "Milligram (mg)": 1e-6,
    "Microgram (µg)": 1e-9,
    "Metric ton (t)": 1000,
    "Pound (lb)": 0.45359237,
    "Ounce (oz)": 0.028349523125,
    "Stone": 6.35029318,
    "Ton (US short ton)": 907.18474,
    "Ton (UK long ton)": 1016.0469088,
}
ENERGY = {
    "Joule (J)": 1,
    "Kilojoule (kJ)": 1000,
    "Megajoule (MJ)": 1e6,
    "Kilowatt-hour (kWh)": 3.6e6,
    "Calorie (cal)": 4.184,
    "Kilocalorie (kcal)": 4184,
    "BTU (British Thermal Unit)": 1055.05585262,
    "Electronvolt (eV)": 1.602176634e-19,
    "Therm (US)": 105480400,
}
POWER = {
    "Watt (W)": 1,
    "Kilowatt (kW)": 1000,
    "Megawatt (MW)": 1e6,
    "Gigawatt (GW)": 1e9,
    "Horsepower (mechanical hp)": 745.699871582,
    "ft-lb/min": 0.0225969658,
}
FLOW = {
    "m³/s": 1,
    "m³/hr": 1 / 3600,
    "L/s": 0.001,
    "L/min": 0.001 / 60,
    "L/hr": 0.001 / 3600,
    "Gallon/min (US GPM)": 6.30901964e-5,
    "Gallon/hr (US GPH)": 1.05150327e-6,
    "ft³/s (CFS)": 0.028316846592,
    "ft³/min (CFM)": 0.028316846592 / 60,
    "Barrel/day (bbl/day)": 0.158987294928 / 86400,
}
DENSITY = {
    "kg/m³": 1,
    "g/cm³": 1000,
    "g/mL": 1000,
    "lb/ft³": 16.01846337,
    "lb/gallon (US)": 119.8264273,
    "lb/gallon (UK)": 99.77637266,
}
DYN_VISC = {
    "Pascal-second (Pa·s)": 1,
    "Millipascal-second (mPa·s)": 0.001,
    "Poise (P)": 0.1,
    "Centipoise (cP)": 0.001,
    "Reyn (lb·s/in²)": 6894.757293168,
}
KIN_VISC = {
    "m²/s": 1,
    "Stoke (St)": 1e-4,
    "Centistoke (cSt)": 1e-6,
}

MASS_FLOW_MASS = {
    "kg/hr": 1,
    "lb/hr": 0.45359237,
    "Metric ton/day": 1000 / 24,
    "US ton/day": 907.18474 / 24,
    "UK ton/day": 1016.0469088 / 24,
}
MASS_FLOW_VOL = {
    "m³/hr": 1,
    "L/hr": 0.001,
    "L/min": 0.06,
    "US GPM": 0.22712470824,
    "US GPH": 0.003785411784,
    "ft³/min (CFM)": 1.69901079552,
    "SCFM (standard ft³/min)": 1.69901079552,
    "ft³/hr": 0.028316846592,
    "Barrel/day (bbl/day)": 0.158987294928 / 24,
}


def num(v, n):
    if v is None or v == "":
        raise ValueError(f"{n} is required.")
    try:
        x = float(v)
    except Exception:
        raise ValueError(f"{n} must be numeric.")
    if not math.isfinite(x):
        raise ValueError(f"{n} must be finite.")
    return x


def pos(v, n):
    x = num(v, n)
    if x <= 0:
        raise ValueError(f"{n} must be greater than zero.")
    return x


def nn(v, n):
    x = num(v, n)
    if x < 0:
        raise ValueError(f"{n} cannot be negative.")
    return x


def fmt(x, d=6):
    if not math.isfinite(x):
        raise ValueError("Result exceeds the supported numeric range.")
    if x != 0 and (abs(x) < 10 ** (-d) or abs(x) >= 1e12):
        return f"{x:.8g}"
    return f"{x:,.{d}f}"


def temperature(v, a, b):
    try:
        v = num(v, "Value")
        c = {
            "Celsius (°C)": v,
            "Fahrenheit (°F)": (v - 32) * 5 / 9,
            "Kelvin (K)": v - 273.15,
            "Rankine (°R)": v * 5 / 9 - 273.15,
        }[a]
        if c < -273.15 - 1e-10:
            raise ValueError("Temperature cannot be below absolute zero.")
        r = {
            "Celsius (°C)": c,
            "Fahrenheit (°F)": c * 9 / 5 + 32,
            "Kelvin (K)": c + 273.15,
            "Rankine (°R)": (c + 273.15) * 9 / 5,
        }[b]
        return f"{v:g} {a} = {fmt(r, 4)} {b}"
    except Exception as e:
        return f"Error: {e}"


def ratio_converter(v, a, b, table):
    try:
        v = num(v, "Value")
        r = v * table[a] / table[b]
        return f"{v:g} {a} = {fmt(r)} {b}"
    except Exception as e:
        return f"Error: {e}"


def mass_flow(v, a, b, rho):
    try:
        v = num(v, "Value")
        fm, tm = a in MASS_FLOW_MASS, b in MASS_FLOW_MASS
        if fm and tm:
            r = v * MASS_FLOW_MASS[a] / MASS_FLOW_MASS[b]
            note = ""
        elif not fm and not tm:
            if a != b and "SCFM (standard ft³/min)" in (a, b):
                raise ValueError("SCFM and actual volume flow require both standard and actual conditions/densities.")
            r = v * MASS_FLOW_VOL[a] / MASS_FLOW_VOL[b]
            note = ""
        else:
            density = pos(rho, "Fluid density")
            if fm:
                r = v * MASS_FLOW_MASS[a] / density / MASS_FLOW_VOL[b]
            else:
                r = v * MASS_FLOW_VOL[a] * density / MASS_FLOW_MASS[b]
            note = f"\nDensity: {density:g} kg/m³ at the volumetric flow reference conditions."
        return f"{v:g} {a} = {fmt(r)} {b}{note}"
    except Exception as e:
        return f"Error: {e}"


def special(v, c):
    try:
        v = num(v, "Value")
        if c == "Specific Gravity to Density (kg/m³)":
            if v <= 0:
                raise ValueError("Specific gravity must be greater than zero.")
            return f"SG {v:g} ≈ {fmt(v*999.016,4)} kg/m³\nReference: water at ~15 °C."
        if c == "Density (kg/m³) to Specific Gravity":
            if v <= 0:
                raise ValueError("Density must be greater than zero.")
            return f"{v:g} kg/m³ ≈ SG {fmt(v/999.016)}"
        if c == "Specific Gravity to API Gravity":
            if v <= 0:
                raise ValueError("Specific gravity must be greater than zero.")
            return f"SG {v:g} = {fmt(141.5/v-131.5,4)} °API"
        if c == "API Gravity to Specific Gravity":
            if v <= -131.5:
                raise ValueError("API gravity must be greater than -131.5.")
            return f"{v:g} °API = SG {fmt(141.5/(v+131.5))}"
        if c == "ppm to percentage (%)":
            return f"{v:g} ppm = {fmt(v/10000,4)} %"
        if c == "Percentage (%) to ppm":
            return f"{v:g} % = {fmt(v*10000,4)} ppm"
        if c != "ppm to mg/L (water approximation)":
            raise ValueError("Unknown calculation.")
        return f"{v:g} ppm ≈ {fmt(v,4)} mg/L\nApproximation applies to dilute aqueous solutions."
    except Exception as e:
        return f"Error: {e}"


def viscosity(v, a, b, rho=None):
    try:
        v = nn(v, "Viscosity")
        ad, bd = a in DYN_VISC, b in DYN_VISC
        if ad and bd:
            r = v * DYN_VISC[a] / DYN_VISC[b]
        elif not ad and not bd:
            r = v * KIN_VISC[a] / KIN_VISC[b]
        elif ad:
            r = v * DYN_VISC[a] / pos(rho, "Fluid density") / KIN_VISC[b]
        else:
            r = v * KIN_VISC[a] * pos(rho, "Fluid density") / DYN_VISC[b]
        return f"{v:g} {a} = {fmt(r)} {b}"
    except Exception as e:
        return f"Error: {e}"


def hcy(r, h, L):
    if h <= 0:
        return 0
    if h >= 2 * r:
        return math.pi * r * r * L
    # Reflect near-full segments to avoid cancellation at either boundary.
    if h > r:
        return math.pi * r * r * L - hcy(r, 2 * r - h, L)
    x = h / r
    if x < 1e-3:
        # Integral of 2*sqrt(2*r*y-y*y), expanded about y/r = 0.
        # Omitted terms have relative magnitude below 2e-16 here.
        A = (4 * math.sqrt(2) / 3) * r * r * x**1.5 * (
            1 - 3*x/20 - 3*x*x/224 - x**3/384
        )
        return A * L
    A = r * r * math.acos((r - h) / r) - (r - h) * math.sqrt(
        max(0, 2 * r * h - h * h)
    )
    return A * L


def sph(r, h):
    if h <= 0:
        return 0
    if h >= 2 * r:
        return 4 * math.pi * r**3 / 3
    return math.pi * h * h * (r - h / 3)


def cone(r, H, h):
    if h <= 0:
        return 0
    if h >= H:
        return math.pi * r * r * H / 3
    return math.pi * r * r * h**3 / (3 * H**2)


def voltxt(v):
    return f"{fmt(v,4)} m³ | {fmt(v*1000,2)} L | {fmt(v*6.28981077,2)} bbl"


def tank(t, D, L, H, W, level, fb):
    try:
        D, L, H, W, level, fb = [
            nn(x, n)
            for x, n in zip(
                [D, L, H, W, level, fb],
                [
                    "Diameter",
                    "Length",
                    "Height",
                    "Width",
                    "Liquid level",
                    "Freeboard",
                ],
            )
        ]
        if t == "Vertical Cylindrical Tank":
            D = pos(D, "Diameter")
            H = pos(H, "Height")
            if level > H or fb > H:
                raise ValueError(
                    "Level/freeboard cannot exceed tank height."
                )
            r = D / 2
            gross = math.pi * r * r * H
            heel = math.pi * r * r * level
            work = math.pi * r * r * (H - fb)
        elif t == "Horizontal Cylindrical Tank":
            D = pos(D, "Diameter")
            L = pos(L, "Length")
            if level > D or fb > D:
                raise ValueError(
                    "Level/freeboard cannot exceed tank diameter."
                )
            r = D / 2
            gross = math.pi * r * r * L
            heel = hcy(r, level, L)
            work = hcy(r, D - fb, L)
        elif t == "Spherical Tank":
            D = pos(D, "Diameter")
            if level > D or fb > D:
                raise ValueError(
                    "Level/freeboard cannot exceed sphere diameter."
                )
            r = D / 2
            gross = 4 * math.pi * r**3 / 3
            heel = sph(r, level)
            work = sph(r, D - fb)
        elif t == "Rectangular Tank":
            L, W, H = pos(L, "Length"), pos(W, "Width"), pos(H, "Height")
            if level > H or fb > H:
                raise ValueError(
                    "Level/freeboard cannot exceed tank height."
                )
            gross = L * W * H
            heel = L * W * level
            work = L * W * (H - fb)
        elif t == "Square Tank":
            W, H = pos(W, "Width"), pos(H, "Height")
            if level > H or fb > H:
                raise ValueError(
                    "Level/freeboard cannot exceed tank height."
                )
            gross = W * W * H
            heel = W * W * level
            work = W * W * (H - fb)
        elif t == "Conical Tank":
            D, H = pos(D, "Diameter"), pos(H, "Height")
            if level > H or fb > H:
                raise ValueError(
                    "Level/freeboard cannot exceed cone height."
                )
            r = D / 2
            gross = math.pi * r * r * H / 3
            heel = cone(r, H, level)
            work = cone(r, H, H - fb)
        else:
            raise ValueError("Unknown tank type.")
        return f"""TANK CALCULATOR RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tank Type: {t}

Gross Capacity:
  {voltxt(gross)}

Capacity Below Freeboard:
  {voltxt(work)}

Heel / Current Liquid Volume:
  {voltxt(heel)}

Free Capacity Above Current Level:
  {voltxt(gross-heel)}

Capacity Below Freeboard / Gross:
  {fmt(work/gross*100,4)} %

Current Fill / Gross:
  {fmt(heel/gross*100,4)} %
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
    except Exception as e:
        return f"Error: {e}"


def pipeline(D, Du, Q, Qu, fluid):
    try:
        D = pos(D, "Pipeline diameter")
        Q = num(Q, "Flow rate")
        if Q < 0:
            raise ValueError("Flow rate cannot be negative.")
        Dm = D * {"mm": 0.001, "inch": 0.0254, "cm": 0.01, "m": 1}[Du]
        A = math.pi * Dm**2 / 4
        q = Q * FLOW[Qu]
        v = q / A
        limits = {
            "Water": (0.5, 2.5),
            "Crude Oil": (0.5, 3),
            "Gasoline/Petrol": (0.5, 3),
            "Diesel": (0.5, 3),
            "Kerosene": (0.5, 3),
            "Heavy Fuel Oil": (0.3, 1.5),
            "LPG (liquid)": (0.5, 2),
            "Chemicals": (0.5, 2),
            "Slurry": (1.5, 3.5),
        }
        lo, hi = limits[fluid]
        status = (
            "⚠️ BELOW SCREENING RANGE"
            if v < lo
            else (
                "⚠️ ABOVE SCREENING RANGE"
                if v > hi
                else "✅ WITHIN SCREENING RANGE"
            )
        )
        return f"""PIPELINE CALCULATOR RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fluid: {fluid}
Internal Diameter: {D:g} {Du} ({fmt(Dm*1000,2)} mm)

AREA
  {fmt(A,4)} m²
  {fmt(A*10000,4)} cm²
  {fmt(A*1550.0031,4)} in²
  {fmt(A*10.7639104,4)} ft²

FLOW
  {fmt(Q,4)} {Qu}
  {fmt(q,4)} m³/s

VELOCITY
  {fmt(v,4)} m/s
  {fmt(v*3.280839895,4)} ft/s
  {fmt(v*60,4)} m/min

SCREENING CHECK
  Generic screening range: {lo:.2f} – {hi:.2f} m/s
  Status: {status}

These velocity limits are generic screening values, not final design criteria."""
    except Exception as e:
        return f"Error: {e}"


def main():
    import streamlit as st
    st.set_page_config(page_title="Conversion Pro", layout="wide")
    st.title("⚙️ Conversion Pro")
    st.caption("Engineering unit conversions, tank geometry and pipeline velocity")

    def number(label, key, value=0.0, nonnegative=False):
        return st.number_input(label, value=float(value), key=key,
                               min_value=0.0 if nonnegative else None, format="%.8g")

    def choice(label, options, key, default=None):
        options = list(options)
        return st.selectbox(label, options, key=key,
                            index=options.index(default) if default else 0)

    def result(text):
        if text.startswith("Error:"):
            st.error(text)
        else:
            st.text(text)

    def basic(label, table, default_a, default_b):
        value = number("Enter value", label + "_value")
        a = choice("From", table, label + "_from", default_a)
        b = choice("To", table, label + "_to", default_b)
        if st.button("Convert", key=label + "_convert"):
            result(temperature(value, a, b) if label == "Temperature"
                   else ratio_converter(value, a, b, table))

    labels = ["Temperature", "Pressure", "Volume", "Mass", "Energy", "Power",
              "Flow Rate", "Mass Flow", "Density", "SG / API / ppm", "Viscosity",
              "Tank Calculator", "Pipeline Calculator", "Advanced Engineering"]
    tabs = st.tabs(labels)
    tables = [(TEMP, TEMP[0], TEMP[1]), (PRESSURE, "Pascal (Pa)", "Bar"),
              (VOLUME, "Liter (L)", "Gallon (US)"), (MASS, "Kilogram (kg)", "Pound (lb)"),
              (ENERGY, "Joule (J)", "Kilojoule (kJ)"), (POWER, "Watt (W)", "Kilowatt (kW)"),
              (FLOW, "m³/s", "L/s")]
    for i, (table, a, b) in enumerate(tables):
        with tabs[i]:
            basic(labels[i], table, a, b)
            if i == 1:
                st.caption("kg/cm² means kg-force/cm²; water/mercury columns use conventional factors. Convert pressures on the same absolute/gauge basis.")
            if i == 4:
                st.caption("Calories are thermochemical; BTU uses the International Table convention.")
    with tabs[7]:
        st.caption("Density must match the flow conditions. SCFM requires density at the specified standard conditions. Signed flow is supported.")
        v = number("Enter value", "mf_value")
        units = list(MASS_FLOW_MASS) + list(MASS_FLOW_VOL)
        a = choice("From", units, "mf_from", "kg/hr")
        b = choice("To", units, "mf_to", "lb/hr")
        rho = number("Fluid density (kg/m³)", "mf_density", 850, True)
        if st.button("Convert", key="mf_convert"):
            result(mass_flow(v, a, b, rho))
    with tabs[8]:
        basic("Density", DENSITY, "kg/m³", "g/cm³")
    with tabs[9]:
        st.caption("SG ↔ density uses water at approximately 15 °C (999.016 kg/m³). API gravity requires SG at 60/60 °F; these reference bases are distinct. ppm ↔ % assumes the same concentration basis.")
        v = number("Enter value", "special_value")
        c = choice("Calculation", ["Specific Gravity to Density (kg/m³)",
            "Density (kg/m³) to Specific Gravity", "Specific Gravity to API Gravity",
            "API Gravity to Specific Gravity", "ppm to percentage (%)",
            "Percentage (%) to ppm", "ppm to mg/L (water approximation)"], "special_calc")
        if st.button("Calculate", key="special_convert"):
            result(special(v, c))
    with tabs[10]:
        st.caption("ν = μ/ρ and μ = νρ. Density and viscosity must refer to the same conditions. SUS is excluded because it is not a constant-factor unit conversion. Reyn means lbf·s/in².")
        v = number("Viscosity", "vis_value", 1, True)
        units = list(DYN_VISC) + list(KIN_VISC)
        a = choice("From", units, "vis_from", "Centipoise (cP)")
        b = choice("To", units, "vis_to", "Centistoke (cSt)")
        rho = number("Fluid density (kg/m³)", "vis_density", 1000, True)
        if st.button("Convert", key="vis_convert"):
            result(viscosity(v, a, b, rho))
    with tabs[11]:
        st.caption("Internal dimensions in metres; level is vertical from the bottom. Cylinders have flat ends. Cone is vertical, apex down, with diameter at the top. Freeboard is measured down from the top. Capacity below freeboard includes the heel; it is not usable capacity after heel subtraction.")
        t = choice("Tank type", ["Vertical Cylindrical Tank", "Horizontal Cylindrical Tank",
                   "Spherical Tank", "Rectangular Tank", "Square Tank", "Conical Tank"], "tank_type")
        required = {"Vertical Cylindrical Tank": "DH", "Horizontal Cylindrical Tank": "DL",
                    "Spherical Tank": "D", "Rectangular Tank": "LHW", "Square Tank": "WH",
                    "Conical Tank": "DH"}[t]
        dims = {k: number(label + " (m)", "tank_" + k, 2, True) if k in required else 0.0
                for k, label in [("D", "Diameter"), ("L", "Length"), ("H", "Height"), ("W", "Width")]}
        level = number("Liquid / heel level (m)", "tank_level", 0, True)
        fb = number("Freeboard (m)", "tank_fb", 0, True)
        if st.button("Calculate tank capacity", key="tank_calculate"):
            result(tank(t, dims['D'], dims['L'], dims['H'], dims['W'], level, fb))
    with tabs[12]:
        D = number("Pipeline internal diameter", "pipe_diameter", 100, True)
        Du = choice("Diameter unit", ["mm", "inch", "cm", "m"], "pipe_du")
        Q = number("Flow rate", "pipe_flow", 10, True)
        Qu = choice("Flow rate unit", FLOW, "pipe_qu", "m³/hr")
        fluid = choice("Fluid", ["Water", "Crude Oil", "Gasoline/Petrol", "Diesel", "Kerosene",
                       "Heavy Fuel Oil", "LPG (liquid)", "Chemicals", "Slurry"], "pipe_fluid")
        if st.button("Calculate", key="pipe_calculate"):
            result(pipeline(D, Du, Q, Qu, fluid))
    with tabs[13]:
        from advanced_engineering import render
        render()
    st.caption("Preliminary engineering calculations. Verify fluid properties, reference conditions and project design criteria before final design use.")


if __name__ == "__main__":
    main()

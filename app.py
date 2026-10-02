"""Year-end LHDN tax refund estimator for YA 2026."""

from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
import streamlit as st

from tax_engine import MONTH_NAMES, Claims, EstimateInput, EstimateResult, estimate

st.set_page_config(
    page_title="LHDN tax refund estimator",
    page_icon=":material/account_balance:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,560;9..144,680&family=Outfit:wght@400;500;600&display=swap');
    html, body, [class*="css"] { font-family: "Outfit", "Segoe UI", sans-serif; }
    .stApp { background: #f3efe6; color: #1c1915; }
    .block-container { padding-top: 1.6rem; max-width: 1180px; }
    h1, h2, h3 { font-family: "Fraunces", Georgia, serif; letter-spacing: -0.02em; }
    .eyebrow {
        letter-spacing: 0.16em; text-transform: uppercase; font-size: 0.74rem;
        color: #8a6232; font-weight: 600; margin-bottom: 0.2rem;
    }
    .hero {
        border-radius: 18px; padding: 1.25rem 1.35rem 1.15rem; color: #f7f2e8;
        box-shadow: 0 12px 30px rgba(28, 25, 21, 0.08);
    }
    .hero.refund { background: #14352c; }
    .hero.payable { background: #6f3228; }
    .hero.settled { background: #243038; }
    .hero .kicker {
        letter-spacing: 0.14em; text-transform: uppercase; font-size: 0.72rem; color: #e4c27a;
    }
    .hero .figure {
        font-family: "Fraunces", Georgia, serif; font-size: 2.8rem; line-height: 1.05;
        margin: 0.3rem 0 0.45rem;
    }
    .hero p { margin: 0; color: #f0e7d8; font-size: 0.98rem; }
    div[data-testid="stMetric"] {
        background: #fffdf8; border: 1px solid #e4dccb; border-radius: 14px; padding: 0.7rem 0.8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

CATEGORIES = {
    "Single": 1,
    "Married, spouse has no income": 2,
    "Married and spouse works, or divorced / widowed": 3,
}
HOUSING = {
    "Not claiming": "none",
    "Home up to RM500,000 (cap RM7,000)": "500",
    "Home RM500,001 to RM750,000 (cap RM5,000)": "750",
}

DEFAULTS = {
    "resident": True,
    "category": "Single",
    "disabled_self": False,
    "disabled_spouse": False,
    "child_u18": 0,
    "child_higher": 0,
    "child_disabled": 0,
    "child_disabled_higher": 0,
    "annual_salary": 0.0,
    "annual_allowance": 0.0,
    "epf_rate": 11.0,
    "epf_exact": False,
    "annual_epf": 0.0,
    "annual_socso": 0.0,
    "bonus": 0.0,
    "bonus_month": "December",
    "bonus_epf_exact": False,
    "bonus_epf": 0.0,
    "other_income": 0.0,
    "start_month": "January",
    "as_of_month": "October",
    "changed_job": False,
    "prev_gross": 0.0,
    "prev_epf": 0.0,
    "prev_pcb": 0.0,
    "prev_reliefs": 0.0,
    "use_actual_pcb": False,
    "actual_pcb": 0.0,
    "zakat": 0.0,
    "zakat_payroll": False,
    "tp1": False,
    "socso_in_pcb": True,
    "parents_medical": 0.0,
    "supporting_equipment": 0.0,
    "education_fees": 0.0,
    "upskilling": 0.0,
    "tourism": 0.0,
    "medical_exam": 0.0,
    "vaccination": 0.0,
    "dental": 0.0,
    "learning_disability": 0.0,
    "serious_medical": 0.0,
    "sspn": 0.0,
    "alimony": 0.0,
    "life_insurance": 0.0,
    "voluntary_epf": 0.0,
    "prs": 0.0,
    "edu_medical_insurance": 0.0,
    "lifestyle": 0.0,
    "breastfeeding": 0.0,
    "childcare": 0.0,
    "sports": 0.0,
    "green_home": 0.0,
    "housing_interest": 0.0,
    "housing_tier": "Not claiming",
}


def ensure_defaults() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)


def apply_preset(updates: dict) -> None:
    st.session_state.update(DEFAULTS)
    st.session_state.update(updates)
    st.rerun()


def money(value: float) -> Decimal:
    return Decimal(f"{float(value):.2f}")


def rm(amount: Decimal) -> str:
    return f"RM {amount:,.2f}"


def epf_on(pay: Decimal, rate: Decimal) -> Decimal:
    return (pay * rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def amount_input(
    label: str,
    key: str,
    help_text: str | None = None,
    maximum: float = 10_000_000.0,
) -> Decimal:
    value = st.number_input(
        label,
        min_value=0.0,
        max_value=maximum,
        step=50.0,
        format="%.2f",
        key=key,
        help=help_text,
    )
    return money(value)


def relief_input(label: str, key: str, cap: int, help_text: str | None = None) -> Decimal:
    """Label ends with /cap so the maximum claim sits next to the field."""
    note = f"The number after / is the maximum. This one stops at RM{cap:,}."
    if help_text:
        note = f"{note} {help_text}"
    return amount_input(f"{label} /{cap:,}", key, note, maximum=float(cap))


def per_month(annual: Decimal, months: int) -> Decimal:
    if months <= 0:
        return Decimal("0.00")
    return (annual / Decimal(months)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_input() -> tuple[EstimateInput, Decimal, Decimal]:
    resident = st.toggle("Malaysian tax resident", key="resident")
    category_label = st.selectbox("Marital status for PCB", list(CATEGORIES), key="category")
    disabled_self = st.checkbox("I am a disabled person (OKU) /7,000", key="disabled_self", help="Extra relief on top of the individual /9,000.")
    disabled_spouse = st.checkbox("My spouse is a disabled person /6,000", key="disabled_spouse", help="Extra relief. It does not replace the spouse /4,000.")

    st.caption(
        "The number after / is the relief for each child. "
        "Count each child once. A disabled child in higher education is /16,000, not also /8,000. "
        "Individual relief /9,000 is added automatically. Spouse relief /4,000 applies only if your spouse has no income."
    )
    child_cols = st.columns(2)
    labels = (
        ("child_u18", "Children under 18 /2,000", "Unmarried and under 18, or still in pre-degree study. RM2,000 for each child."),
        ("child_higher", "Children in diploma or degree /8,000", "Diploma or higher in Malaysia, or a degree or higher overseas. RM8,000 for each child."),
        ("child_disabled", "Disabled children /8,000", "Certified by the Department of Social Welfare. RM8,000 for each child."),
        ("child_disabled_higher", "Disabled children in higher education /16,000", "Diploma or higher. RM16,000 for each child. Do not also count them above."),
    )
    children = []
    for index, (key, label, help_text) in enumerate(labels):
        with child_cols[index % 2]:
            children.append(
                int(st.number_input(label, min_value=0, max_value=15, step=1, key=key, help=help_text))
            )

    st.subheader("Income for the year")
    annual_salary = amount_input(
        "Annual gross salary",
        "annual_salary",
        "Total basic pay for this year, before EPF. If you joined mid-year, enter only what this employer pays you.",
    )
    annual_allowance = amount_input(
        "Other taxable pay for the year",
        "annual_allowance",
        "Taxable fixed allowances or benefits for the year. Leave out exempt items such as parking and official petrol within the exempt limit.",
    )
    timing = st.columns(2)
    with timing[0]:
        start_month = MONTH_NAMES.index(st.selectbox("I joined this employer in", MONTH_NAMES, key="start_month")) + 1
    with timing[1]:
        as_of = MONTH_NAMES.index(st.selectbox("Show the payslip for", MONTH_NAMES, key="as_of_month")) + 1
    months_worked = 13 - start_month
    monthly_salary = per_month(annual_salary, months_worked)
    monthly_allowance = per_month(annual_allowance, months_worked)
    if annual_salary > 0 or annual_allowance > 0:
        st.caption(
            f"Spread over {months_worked} months: {rm(monthly_salary)} salary"
            + (f" and {rm(monthly_allowance)} other pay" if annual_allowance else "")
            + " a month."
        )

    rate = money(st.number_input("Employee EPF rate (%)", min_value=0.0, max_value=20.0, step=0.5, key="epf_rate", help="EPF relief is /4,000 for the year, even if you contribute more."))
    exact_epf = st.checkbox("Use my exact EPF for the year", key="epf_exact")
    if exact_epf:
        annual_epf = amount_input("EPF deducted this year /4,000", "annual_epf", "Enter the full amount deducted. Only /4,000 reduces your tax.")
        monthly_epf = per_month(annual_epf, months_worked)
    else:
        monthly_epf = epf_on(monthly_salary, rate)
        annual_epf = (monthly_epf * Decimal(months_worked)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        st.caption(f"EPF used: {rm(annual_epf)} for the year ({rm(monthly_epf)} a month). Relief stops at /4,000.")

    annual_socso = relief_input(
        "SOCSO and EIS for the year",
        "annual_socso",
        350,
        "Employee share only. Anything above /350 is ignored.",
    )

    bonus_cols = st.columns(2)
    with bonus_cols[0]:
        bonus = amount_input("Bonus or other one-off pay", "bonus", "Commission, arrears, or a bonus paid in one month.")
    with bonus_cols[1]:
        bonus_month = MONTH_NAMES.index(st.selectbox("Paid in", MONTH_NAMES, key="bonus_month")) + 1
    exact_bonus_epf = st.checkbox("Use an exact EPF amount on that bonus", key="bonus_epf_exact")
    if exact_bonus_epf:
        bonus_epf = amount_input("EPF on the bonus", "bonus_epf")
    else:
        bonus_epf = epf_on(bonus, rate)
        if bonus > 0:
            st.caption(f"EPF on the bonus: {rm(bonus_epf)}.")

    other_income = amount_input(
        "Other taxable income for the year",
        "other_income",
        "Rent, business, or freelance income. This is not in your monthly PCB, so it can leave tax to pay.",
    )

    with st.expander("Previous employer this year"):
        st.checkbox("I changed jobs during this year", key="changed_job")
        prev_gross = amount_input("Gross pay from the previous employer", "prev_gross")
        prev_epf = amount_input("EPF already deducted there", "prev_epf")
        prev_pcb = amount_input("PCB already deducted there", "prev_pcb")
        prev_reliefs = amount_input("Reliefs already claimed there (TP3)", "prev_reliefs")

    with st.expander("PCB already on my payslips"):
        st.checkbox("Use my own year-to-date PCB instead of the estimate", key="use_actual_pcb")
        actual_pcb = amount_input(
            "PCB deducted before the payslip month above",
            "actual_pcb",
            "Add up PCB on payslips from January through the month before the one you selected.",
        )

    st.subheader("Reliefs you will claim")
    st.caption("The number after / is the maximum for that claim. These cut monthly PCB only if your employer has them on Borang TP1.")
    tp1 = st.checkbox("My employer already uses these reliefs (I submitted TP1)", key="tp1")
    socso_in_pcb = st.checkbox("Payroll already includes my SOCSO and EIS in PCB", key="socso_in_pcb")

    with st.expander("Family, education and savings"):
        education_fees = relief_input("Education fees (self)", "education_fees", 7000, "Shares /7,000 with upskilling courses.")
        upskilling = relief_input("Upskilling courses", "upskilling", 2000, "This /2,000 sits inside the education /7,000, it is not extra.")
        childcare = relief_input("Childcare, kindergarten or transit fees", "childcare", 3000, "Registered centres, children up to 12. Either parent claims it.")
        sspn = relief_input("SSPN net deposit", "sspn", 8000, "Deposits minus withdrawals. Either parent claims it.")
        alimony = relief_input("Alimony to a former wife", "alimony", 4000, "Not on top of the spouse /4,000.")
        breastfeeding = relief_input("Breastfeeding equipment", "breastfeeding", 1000, "Once in two years.")

    with st.expander("Health"):
        st.caption("Serious illness, learning disability, check-ups, vaccination and dental share one /10,000 for yourself, your spouse and children.")
        serious_medical = relief_input("Serious disease and fertility treatment", "serious_medical", 10000, "Inside the shared /10,000.")
        learning = relief_input(
            "Learning-disability assessment and therapy",
            "learning_disability",
            10000,
            "Diagnosis, early intervention and rehabilitation for a child aged 18 or under. Inside the shared /10,000.",
        )
        medical_exam = relief_input("Full medical examination and self-test devices", "medical_exam", 1000, "Inside the shared /10,000.")
        vaccination = relief_input("Vaccination", "vaccination", 1000, "All NPRA-registered vaccines. Inside the shared /10,000.")
        dental = relief_input("Dental examination and treatment", "dental", 1000, "Inside the shared /10,000.")
        parents_medical = relief_input("Parents or grandparents", "parents_medical", 8000, "Medical treatment, special needs and carer. A full check-up inside this is /1,000.")
        equipment = relief_input("Basic supporting equipment for a disabled person", "supporting_equipment", 6000, "Excludes optical lenses and spectacles.")

    with st.expander("Insurance and retirement"):
        life = relief_input("Life insurance or family takaful", "life_insurance", 3000, "Self, spouse and eligible children.")
        voluntary_epf = relief_input(
            "Voluntary EPF",
            "voluntary_epf",
            7000,
            "With compulsory EPF, only the unused part of /4,000 counts. With no compulsory EPF, this and life insurance together stop at /7,000.",
        )
        prs = relief_input("PRS or deferred annuity", "prs", 3000)
        edu_ins = relief_input("Education or medical insurance", "edu_medical_insurance", 4000, "Self, spouse and eligible children.")

    with st.expander("Lifestyle, home and other"):
        lifestyle = relief_input("Lifestyle", "lifestyle", 2500, "Books, computer, smartphone, tablet, internet, and self-enrichment.")
        sports = relief_input("Sports equipment, facilities and gym", "sports", 1000, "On top of the lifestyle /2,500.")
        tourism = relief_input("Tourist attractions and cultural programmes", "tourism", 1000, "Admission fees for 2026 only.")
        green = relief_input("EV charger, composter, food-waste grinder or home CCTV", "green_home", 2500, "The grinder and CCTV can be claimed once across 2026 and 2027.")
        housing_tier = st.selectbox("First home bought from 2025 to 2027", list(HOUSING), key="housing_tier")
        housing_cap = {"none": 0, "500": 7000, "750": 5000}[HOUSING[housing_tier]]
        housing_label = "Housing-loan interest paid this year"
        if housing_cap:
            housing_label = f"{housing_label} /{housing_cap:,}"
        housing_interest = amount_input(
            housing_label,
            "housing_interest",
            "First home only, for three consecutive years. /7,000 if the home is up to RM500,000. /5,000 if it is RM500,001 to RM750,000.",
        )

    zakat_cols = st.columns(2)
    with zakat_cols[0]:
        zakat = amount_input("Zakat paid or to be paid this year", "zakat")
    with zakat_cols[1]:
        zakat_payroll = st.checkbox("Employer deducts this zakat from PCB", key="zakat_payroll")

    claims = Claims(
        parents_medical=parents_medical,
        supporting_equipment=equipment,
        education_fees=education_fees,
        upskilling=upskilling,
        tourism=tourism,
        medical_exam=medical_exam,
        vaccination=vaccination,
        dental=dental,
        learning_disability=learning,
        serious_medical=serious_medical,
        sspn=sspn,
        alimony=alimony,
        life_insurance=life,
        voluntary_epf=voluntary_epf,
        prs=prs,
        edu_medical_insurance=edu_ins,
        socso=annual_socso,
        lifestyle=lifestyle,
        breastfeeding=breastfeeding,
        childcare=childcare,
        sports=sports,
        green_home=green,
        housing_interest=housing_interest,
        housing_tier=HOUSING[housing_tier],
    )
    data = EstimateInput(
        resident=resident,
        category=CATEGORIES[category_label],
        disabled_self=disabled_self,
        disabled_spouse=disabled_spouse,
        children_under_18=children[0],
        children_higher=children[1],
        children_disabled=children[2],
        children_disabled_higher=children[3],
        monthly_salary=monthly_salary,
        monthly_allowance=monthly_allowance,
        monthly_epf=monthly_epf,
        bonus=bonus,
        bonus_epf=bonus_epf,
        bonus_month=bonus_month,
        other_income=other_income,
        start_month=start_month,
        as_of_month=as_of,
        prev_gross=prev_gross if st.session_state.changed_job else Decimal("0"),
        prev_epf=prev_epf if st.session_state.changed_job else Decimal("0"),
        prev_pcb=prev_pcb if st.session_state.changed_job else Decimal("0"),
        prev_reliefs=prev_reliefs if st.session_state.changed_job else Decimal("0"),
        actual_pcb_before=actual_pcb if st.session_state.use_actual_pcb else None,
        zakat=zakat,
        zakat_via_payroll=zakat_payroll,
        tp1_submitted=tp1,
        socso_in_pcb=socso_in_pcb,
        claims=claims,
    )
    return data, monthly_epf, bonus_epf


def render_result(result: EstimateResult) -> None:
    if result.annual_income <= 0:
        st.markdown(
            """
            <div class="hero settled">
                <div class="kicker">Year-end position</div>
                <div class="figure">Enter your salary</div>
                <p>Add your annual pay, EPF and any reliefs. The number after / on a relief is the maximum you can claim.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    if result.position == "refund":
        title = "Estimated refund"
        css = "refund"
        sentence = (
            f"PCB sent to LHDN for the year is {rm(result.pcb_to_lhdn)}. "
            f"Tax on these figures is {rm(result.tax_payable)}. "
            "The difference is the refund to expect after you file."
        )
    elif result.position == "payable":
        title = "Estimated tax still to pay"
        css = "payable"
        sentence = (
            f"Tax on these figures is {rm(result.tax_payable)}. "
            f"PCB covers {rm(result.pcb_to_lhdn)}. "
            "The shortfall is what you should expect to pay when you file."
        )
    else:
        title = "Nothing to refund or pay"
        css = "settled"
        sentence = "Monthly PCB for the year matches the tax on these figures."

    st.markdown(
        f"""
        <div class="hero {css}">
            <div class="kicker">{title}</div>
            <div class="figure">{rm(abs(result.balance))}</div>
            <p>{sentence}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    month_name = MONTH_NAMES[result.as_of_month - 1]
    summary = st.columns(2)
    summary[0].write(f"Tax payable  \n**{rm(result.tax_payable)}**")
    summary[1].write(f"PCB for the year  \n**{rm(result.pcb_to_lhdn)}**")
    summary = st.columns(2)
    summary[0].write(f"{month_name} payslip PCB  \n**{rm(result.pcb_this_month)}**")
    summary[1].write(f"{month_name} to December  \n**{rm(result.pcb_still_to_deduct)}**")


def render_schedule(result: EstimateResult) -> None:
    st.subheader("Month-by-month PCB")
    st.caption("Additional PCB is the extra deduction in a bonus month. It is the tax on that payment, taken in one go.")
    frame = pd.DataFrame(
        [
            {
                "Month": row.name,
                "Salary": float(row.salary),
                "Additional pay": float(row.additional),
                "Projected chargeable income": float(row.chargeable_projected),
                "Normal PCB": float(row.pcb_normal),
                "Additional PCB": float(row.pcb_additional),
                "PCB": float(row.pcb),
            }
            for row in result.months
        ]
    )
    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        column_config={
            "Salary": st.column_config.NumberColumn(format="RM %.2f"),
            "Additional pay": st.column_config.NumberColumn(format="RM %.2f"),
            "Projected chargeable income": st.column_config.NumberColumn(format="RM %.2f"),
            "Normal PCB": st.column_config.NumberColumn(format="RM %.2f"),
            "Additional PCB": st.column_config.NumberColumn(format="RM %.2f"),
            "PCB": st.column_config.NumberColumn(format="RM %.2f"),
        },
    )


ensure_defaults()

st.markdown('<div class="eyebrow">Year of assessment 2026</div>', unsafe_allow_html=True)
st.title("How much tax comes back")
st.write(
    "Enter annual salary and the reliefs you will claim. The number after / is that relief’s cap. "
    "PCB is still worked out month by month from the 2026 formula."
)

preset_cols = st.columns(3)
with preset_cols[0]:
    if st.button("RM72,000 a year", width="stretch"):
        apply_preset({"annual_salary": 72000.0, "epf_rate": 11.0, "as_of_month": "January"})
with preset_cols[1]:
    if st.button("Lifestyle refund", width="stretch"):
        apply_preset({"annual_salary": 72000.0, "epf_rate": 11.0, "lifestyle": 2500.0, "tp1": False})
with preset_cols[2]:
    if st.button("Married, with bonus", width="stretch"):
        apply_preset(
            {
                "category": "Married and spouse works, or divorced / widowed",
                "child_u18": 3,
                "annual_salary": 66000.0,
                "epf_exact": True,
                "annual_epf": 7260.0,
                "bonus": 8250.0,
                "bonus_month": "April",
                "bonus_epf_exact": True,
                "bonus_epf": 908.0,
                "as_of_month": "January",
            }
        )

hero_slot = st.empty()
inputs, right = st.columns([1.15, 0.85], gap="large")
with inputs:
    st.subheader("Your details")
    data, _, _ = build_input()

result = estimate(data)

with hero_slot.container():
    render_result(result)

with right:
    if result.annual_income > 0:
        st.subheader("Breakdown")
        for label, amount in result.income_lines:
            st.write(f"{label}: {rm(amount)}")
        st.write(f"Total income: {rm(result.annual_income)}")
        st.write(f"Total reliefs: {rm(result.total_reliefs)}")
        st.write(f"Chargeable income: {rm(result.chargeable)}")
        st.caption(result.band)
        st.write(f"Tax before rebate: {rm(result.tax_before_rebate)}")
        if result.rebate:
            st.write(f"Personal rebate: {rm(result.rebate)}")
        if result.zakat_rebate:
            st.write(f"Zakat rebate: {rm(result.zakat_rebate)}")
        with st.expander("Reliefs counted"):
            if result.relief_lines:
                for label, amount in result.relief_lines:
                    st.write(f"{label}: {rm(amount)}")
            else:
                st.write("No resident reliefs are applied.")
        if result.notes:
            with st.expander("Assumptions"):
                for note in result.notes:
                    st.write(note)

if result.annual_income > 0:
    st.divider()
    render_schedule(result)

with st.expander("What this follows"):
    st.markdown(
        """
        Monthly PCB for a resident is:

        `[(P − M) × R + B − (Z + X)] ÷ (months left, including this month)`

        `P` is the year's projected chargeable income. The employer annualises your current salary,
        subtracts EPF up to RM4,000, the RM9,000 individual relief, spouse and child relief where
        they apply, and any TP1 reliefs already submitted. Tax rates are the resident scale used
        since YA 2023 and carried into the 2026 specification. Figures in the formula are cut off
        at the sen, then PCB is rounded up to the next 5 sen. Under RM10, no PCB is deducted.

        A refund appears when the PCB withheld during the year is higher than the tax after every
        relief you claim at e-Filing. Extra income that never went through PCB does the opposite.

        This is an estimate, not a notice from HASiL and not advice for your return. Special rates
        for the Returning Expert Programme, knowledge workers and C-suite non-citizens are not included.
        Check the figures against the official calculator before you file.
        """
    )
    st.markdown(
        "[Official PCB calculator (YA 2026)](https://calcpcbplus.hasil.gov.my/HITS_CE/x2026?PRV_YEAR=true&FRS_REC=true) · "
        "[2026 MTD specification](https://www.hasil.gov.my/media/arvlrzh5/spesifikasi-kaedah-pengiraan-berkomputer-pcb-2026.pdf) · "
        "[Tax rates](https://www.hasil.gov.my/en/individu/kadar-cukai/)"
    )

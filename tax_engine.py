"""Year-of-assessment 2026 resident PCB and tax-refund estimate.

The monthly deduction follows Lembaga Hasil Dalam Negeri Malaysia's
computerised Monthly Tax Deduction formula for 2026. There is no change
to that formula for 2026; Budget 2026 changes the relief amounts that
can be fed into it.

Source: Specification for Monthly Tax Deduction (MTD) Calculations Using
Computerized Calculation for 2026 (updated 1 January 2026).
https://www.hasil.gov.my/media/arvlrzh5/spesifikasi-kaedah-pengiraan-berkomputer-pcb-2026.pdf
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

TWOPLACES = Decimal("0.01")
EPF_CAP = Decimal("4000")
LIFE_CAP = Decimal("3000")
EPF_LIFE_CAP = Decimal("7000")
INDIVIDUAL_RELIEF = Decimal("9000")
SPOUSE_RELIEF = Decimal("4000")
DISABLED_SELF_RELIEF = Decimal("7000")
DISABLED_SPOUSE_RELIEF = Decimal("6000")
CHILD_UNDER_18 = Decimal("2000")
CHILD_HIGHER = Decimal("8000")
CHILD_DISABLED = Decimal("8000")
CHILD_DISABLED_HIGHER = Decimal("16000")
MEDICAL_CAP = Decimal("10000")
SOCSO_CAP = Decimal("350")
NON_RESIDENT_RATE = Decimal("0.30")
MIN_MTD = Decimal("10")

# (ceiling, floor M, rate, tax already charged on M)
BRACKETS = (
    (Decimal("20000"), Decimal("5000"), Decimal("0.01"), Decimal("0")),
    (Decimal("35000"), Decimal("20000"), Decimal("0.03"), Decimal("150")),
    (Decimal("50000"), Decimal("35000"), Decimal("0.06"), Decimal("600")),
    (Decimal("70000"), Decimal("50000"), Decimal("0.11"), Decimal("1500")),
    (Decimal("100000"), Decimal("70000"), Decimal("0.19"), Decimal("3700")),
    (Decimal("400000"), Decimal("100000"), Decimal("0.25"), Decimal("9400")),
    (Decimal("600000"), Decimal("400000"), Decimal("0.26"), Decimal("84400")),
    (Decimal("2000000"), Decimal("600000"), Decimal("0.28"), Decimal("136400")),
    (None, Decimal("2000000"), Decimal("0.30"), Decimal("528400")),
)

# Rebate is already inside B for the two lowest bands. Category 2 gets the
# spouse rebate as well (RM400 + RM400) when chargeable income is RM35,000 or less.
REBATE_ADJUSTMENT = {
    1: (Decimal("-400"), Decimal("-250")),
    2: (Decimal("-800"), Decimal("-650")),
    3: (Decimal("-400"), Decimal("-250")),
}

BAND_LABELS = (
    (Decimal("5000"), "0% on the first RM5,000"),
    (Decimal("20000"), "1% band, RM5,001 – RM20,000"),
    (Decimal("35000"), "3% band, RM20,001 – RM35,000"),
    (Decimal("50000"), "6% band, RM35,001 – RM50,000"),
    (Decimal("70000"), "11% band, RM50,001 – RM70,000"),
    (Decimal("100000"), "19% band, RM70,001 – RM100,000"),
    (Decimal("400000"), "25% band, RM100,001 – RM400,000"),
    (Decimal("600000"), "26% band, RM400,001 – RM600,000"),
    (Decimal("2000000"), "28% band, RM600,001 – RM2,000,000"),
    (None, "30% band, above RM2,000,000"),
)

MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def D(value: Decimal | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def trunc2(amount: Decimal) -> Decimal:
    """Drop every digit after the sen. LHDN does not round these figures."""
    return amount.quantize(TWOPLACES, rounding=ROUND_DOWN)


def round_up_5sen(amount: Decimal) -> Decimal:
    """Round a Monthly Tax Deduction up to the next 5 sen."""
    amount = trunc2(amount)
    if amount <= 0:
        return Decimal("0.00")
    sen = (amount * 100).to_integral_value(rounding=ROUND_DOWN)
    remainder = sen % 5
    if remainder:
        sen += 5 - remainder
    return (sen / Decimal(100)).quantize(TWOPLACES)


def finalize_mtd(raw: Decimal) -> Decimal:
    """Truncate, round up to 5 sen, and drop any deduction under RM10."""
    rounded = round_up_5sen(raw)
    if rounded < MIN_MTD:
        return Decimal("0.00")
    return rounded


def band_label(chargeable: Decimal) -> str:
    if chargeable <= 0:
        return "No chargeable income"
    for ceiling, label in BAND_LABELS:
        if ceiling is None or chargeable <= ceiling:
            return label
    return BAND_LABELS[-1][1]


def statutory_tax(chargeable: Decimal) -> Decimal:
    """Tax from the resident scale, before the personal rebate."""
    if chargeable <= Decimal("5000"):
        return Decimal("0.00")
    for ceiling, floor, rate, base in BRACKETS:
        if ceiling is None or chargeable <= ceiling:
            return trunc2((chargeable - floor) * rate) + base
    return Decimal("0.00")


def personal_rebate(chargeable: Decimal, category: int) -> Decimal:
    if chargeable <= 0 or chargeable > Decimal("35000"):
        return Decimal("0.00")
    return Decimal("800.00") if category == 2 else Decimal("400.00")


def pcb_tax_on_p(chargeable: Decimal, category: int) -> Decimal:
    """[(P - M) x R] + B, with B already reduced by the rebate."""
    if chargeable <= Decimal("5000"):
        return Decimal("0.00")
    gross = statutory_tax(chargeable)
    if chargeable <= Decimal("20000"):
        return gross + REBATE_ADJUSTMENT[category][0]
    if chargeable <= Decimal("35000"):
        return gross + REBATE_ADJUSTMENT[category][1]
    return gross


def child_relief_amount(
    under_18: int,
    higher_education: int,
    disabled: int,
    disabled_higher: int,
) -> Decimal:
    return (
        Decimal(under_18) * CHILD_UNDER_18
        + Decimal(higher_education) * CHILD_HIGHER
        + Decimal(disabled) * CHILD_DISABLED
        + Decimal(disabled_higher) * CHILD_DISABLED_HIGHER
    )


def fixed_deductions(
    category: int,
    disabled_self: bool,
    disabled_spouse: bool,
    children: Decimal,
) -> tuple[Decimal, list[tuple[str, Decimal]]]:
    lines: list[tuple[str, Decimal]] = [("Individual and dependent relatives", INDIVIDUAL_RELIEF)]
    total = INDIVIDUAL_RELIEF
    if category == 2:
        lines.append(("Spouse with no income", SPOUSE_RELIEF))
        total += SPOUSE_RELIEF
    if disabled_self:
        lines.append(("Disabled individual, additional", DISABLED_SELF_RELIEF))
        total += DISABLED_SELF_RELIEF
    if disabled_spouse and category in (2, 3):
        lines.append(("Disabled spouse, additional", DISABLED_SPOUSE_RELIEF))
        total += DISABLED_SPOUSE_RELIEF
    if children > 0:
        lines.append(("Qualifying children", children))
        total += children
    return total, lines


def epf_and_life_relief(
    mandatory_epf: Decimal,
    voluntary_epf: Decimal,
    life_insurance: Decimal,
) -> tuple[Decimal, Decimal]:
    """Split EPF and life insurance into the RM4,000 and RM3,000 limits.

    Mandatory EPF uses the RM4,000 limit first. Voluntary EPF fills whatever
    remains of that limit. With no mandatory contribution, voluntary EPF can
    also use the RM3,000 life-insurance limit, up to RM7,000 combined.
    """
    mandatory_epf = max(Decimal("0"), mandatory_epf)
    voluntary_epf = max(Decimal("0"), voluntary_epf)
    life_insurance = min(max(Decimal("0"), life_insurance), LIFE_CAP)

    if mandatory_epf > 0:
        epf_relief = min(mandatory_epf + voluntary_epf, EPF_CAP)
        return epf_relief, life_insurance

    epf_relief = min(voluntary_epf, EPF_CAP)
    leftover_voluntary = voluntary_epf - epf_relief
    life_relief = min(life_insurance + leftover_voluntary, LIFE_CAP)
    return epf_relief, life_relief


@dataclass
class Claims:
    parents_medical: Decimal = Decimal("0")
    supporting_equipment: Decimal = Decimal("0")
    education_fees: Decimal = Decimal("0")
    upskilling: Decimal = Decimal("0")
    tourism: Decimal = Decimal("0")
    medical_exam: Decimal = Decimal("0")
    vaccination: Decimal = Decimal("0")
    dental: Decimal = Decimal("0")
    learning_disability: Decimal = Decimal("0")
    serious_medical: Decimal = Decimal("0")
    sspn: Decimal = Decimal("0")
    alimony: Decimal = Decimal("0")
    life_insurance: Decimal = Decimal("0")
    voluntary_epf: Decimal = Decimal("0")
    prs: Decimal = Decimal("0")
    edu_medical_insurance: Decimal = Decimal("0")
    socso: Decimal = Decimal("0")
    lifestyle: Decimal = Decimal("0")
    breastfeeding: Decimal = Decimal("0")
    childcare: Decimal = Decimal("0")
    sports: Decimal = Decimal("0")
    green_home: Decimal = Decimal("0")
    housing_interest: Decimal = Decimal("0")
    housing_tier: str = "none"


@dataclass
class ReliefBreakdown:
    lines: list[tuple[str, Decimal]]
    total: Decimal
    optional_for_tp1: Decimal
    socso: Decimal
    notes: list[str] = field(default_factory=list)


def _cap(amount: Decimal, limit: Decimal) -> Decimal:
    return min(max(D(amount), Decimal("0")), limit)


def apply_claims(
    claims: Claims,
    category: int,
    mandatory_epf: Decimal,
    auto_lines: list[tuple[str, Decimal]],
    auto_total: Decimal,
) -> ReliefBreakdown:
    notes: list[str] = []
    lines = list(auto_lines)
    total = auto_total

    epf_relief, life_relief = epf_and_life_relief(
        mandatory_epf, claims.voluntary_epf, claims.life_insurance
    )
    if epf_relief > 0:
        lines.append(("EPF and approved scheme", epf_relief))
        total += epf_relief
        contributed = mandatory_epf + max(D(claims.voluntary_epf), Decimal("0"))
        if contributed > epf_relief:
            notes.append("EPF relief is capped at RM4,000 for the year.")
    if life_relief > 0:
        lines.append(("Life insurance or takaful", life_relief))
        total += life_relief

    # Payroll already reduces PCB through K for mandatory EPF. Anything claimed
    # on TP1 — life insurance, and voluntary EPF that still fits under the cap —
    # has to be passed in separately as LP.
    optional = life_relief
    payroll_epf = min(max(mandatory_epf, Decimal("0")), EPF_CAP)
    voluntary_not_in_payroll = epf_relief - payroll_epf
    if voluntary_not_in_payroll > 0:
        optional += voluntary_not_in_payroll

    def add(label: str, amount: Decimal, counts_for_tp1: bool = True) -> None:
        nonlocal total, optional
        if amount <= 0:
            return
        lines.append((label, amount))
        total += amount
        if counts_for_tp1:
            optional += amount

    medical_parts = (
        _cap(claims.medical_exam, Decimal("1000")),
        _cap(claims.vaccination, Decimal("1000")),
        _cap(claims.dental, Decimal("1000")),
        _cap(claims.learning_disability, MEDICAL_CAP),
        _cap(claims.serious_medical, MEDICAL_CAP),
    )
    medical_raw = sum(medical_parts, Decimal("0"))
    medical = min(medical_raw, MEDICAL_CAP)
    if medical_raw > MEDICAL_CAP:
        notes.append(
            "Medical expenses for yourself, your spouse and children share one RM10,000 limit."
        )
    add("Medical for self, spouse and children", medical)

    add("Parents and grandparents medical", _cap(claims.parents_medical, Decimal("8000")))
    add("Basic supporting equipment", _cap(claims.supporting_equipment, Decimal("6000")))

    education = min(
        max(D(claims.education_fees), Decimal("0")) + _cap(claims.upskilling, Decimal("2000")),
        Decimal("7000"),
    )
    if (
        max(D(claims.education_fees), Decimal("0")) + _cap(claims.upskilling, Decimal("2000"))
        > Decimal("7000")
    ):
        notes.append(
            "Study fees and upskilling courses share one RM7,000 limit. Upskilling inside that limit is capped at RM2,000."
        )
    add("Education fees and upskilling", education)

    add("Domestic tourism and cultural admission", _cap(claims.tourism, Decimal("1000")))
    add("SSPN net deposit", _cap(claims.sspn, Decimal("8000")))

    alimony = _cap(claims.alimony, Decimal("4000"))
    if category == 2 and alimony > 0:
        alimony = Decimal("0")
        notes.append(
            "Alimony is not added on top of the RM4,000 spouse relief. The two together cannot exceed RM4,000."
        )
    elif category == 1 and alimony > 0:
        alimony = Decimal("0")
        notes.append("Alimony relief applies if you are divorced or separated and paying a former wife.")
    add("Alimony to a former wife", alimony)

    add("Private retirement scheme and deferred annuity", _cap(claims.prs, Decimal("3000")))
    add(
        "Education and medical insurance",
        _cap(claims.edu_medical_insurance, Decimal("4000")),
    )

    socso = _cap(claims.socso, SOCSO_CAP)
    if max(D(claims.socso), Decimal("0")) > SOCSO_CAP:
        notes.append("SOCSO and EIS relief is capped at RM350.")
    add("SOCSO and EIS", socso, counts_for_tp1=False)

    add("Lifestyle", _cap(claims.lifestyle, Decimal("2500")))
    add("Breastfeeding equipment", _cap(claims.breastfeeding, Decimal("1000")))
    add("Childcare and registered transit fees", _cap(claims.childcare, Decimal("3000")))
    add("Sports and gym", _cap(claims.sports, Decimal("1000")))
    add("EV charging, composter, food-waste grinder or home CCTV", _cap(claims.green_home, Decimal("2500")))

    if claims.housing_tier == "500":
        housing_cap = Decimal("7000")
    elif claims.housing_tier == "750":
        housing_cap = Decimal("5000")
    else:
        housing_cap = Decimal("0")
    add("First-home loan interest", _cap(claims.housing_interest, housing_cap) if housing_cap else Decimal("0"))

    return ReliefBreakdown(
        lines=lines,
        total=total,
        optional_for_tp1=optional,
        socso=socso,
        notes=notes,
    )


@dataclass
class ComputeResult:
    p_normal: Decimal
    p: Decimal
    k1: Decimal
    kt: Decimal
    k2: Decimal
    annual_tax_normal: Decimal
    annual_tax: Decimal
    mtd_normal: Decimal
    mtd_additional: Decimal
    mtd: Decimal


def _qualifying_epf(
    k_acc: Decimal,
    epf_month: Decimal,
    epf_additional: Decimal,
    months_after: int,
) -> tuple[Decimal, Decimal, Decimal]:
    k1 = min(max(epf_month, Decimal("0")), max(EPF_CAP - k_acc, Decimal("0")))
    k1 = trunc2(k1)
    kt = min(max(epf_additional, Decimal("0")), max(EPF_CAP - k_acc - k1, Decimal("0")))
    kt = trunc2(kt)
    if months_after <= 0:
        return k1, kt, Decimal("0.00")
    remaining = EPF_CAP - k_acc - k1 - kt
    if remaining < 0:
        remaining = Decimal("0")
    spread = trunc2(remaining / Decimal(months_after))
    k2 = min(max(epf_month, Decimal("0")), spread)
    return k1, kt, trunc2(k2)


def _chargeable(
    y_acc: Decimal,
    k_acc: Decimal,
    y1: Decimal,
    k1: Decimal,
    k2: Decimal,
    months_after: int,
    yt: Decimal,
    kt: Decimal,
    fixed: Decimal,
    lp_acc: Decimal,
    lp1: Decimal,
) -> Decimal:
    net_prior = trunc2(y_acc - k_acc)
    net_current = trunc2(y1 - k1)
    future_monthly = trunc2(y1 - k2)
    future = trunc2(future_monthly * Decimal(months_after))
    net_additional = trunc2(yt - kt)
    total = net_prior + net_current + future + net_additional - fixed - lp_acc - lp1
    return trunc2(total)


def compute_month(
    y_acc: Decimal,
    k_acc: Decimal,
    x_acc: Decimal,
    z_acc: Decimal,
    lp_acc: Decimal,
    y1: Decimal,
    epf_month: Decimal,
    yt: Decimal,
    epf_additional: Decimal,
    lp1: Decimal,
    months_after: int,
    category: int,
    fixed: Decimal,
) -> ComputeResult:
    """One month of the resident computerised PCB formula."""
    k1_n, kt_n, k2_n = _qualifying_epf(k_acc, epf_month, Decimal("0"), months_after)
    p_normal = _chargeable(
        y_acc, k_acc, y1, k1_n, k2_n, months_after, Decimal("0"), Decimal("0"), fixed, lp_acc, lp1
    )
    annual_normal = pcb_tax_on_p(p_normal, category)
    mtd_normal = finalize_mtd((annual_normal - (z_acc + x_acc)) / Decimal(months_after + 1))

    has_additional = yt > 0 or epf_additional > 0
    if has_additional:
        k1, kt, k2 = _qualifying_epf(k_acc, epf_month, epf_additional, months_after)
        p = _chargeable(
            y_acc, k_acc, y1, k1, k2, months_after, yt, kt, fixed, lp_acc, lp1
        )
        annual = pcb_tax_on_p(p, category)
        reserved = x_acc + (mtd_normal * Decimal(months_after + 1))
        mtd_additional = finalize_mtd(annual - reserved + z_acc)
    else:
        k1, kt, k2 = k1_n, kt_n, k2_n
        p = p_normal
        annual = annual_normal
        mtd_additional = Decimal("0.00")

    return ComputeResult(
        p_normal=p_normal,
        p=p,
        k1=k1,
        kt=kt,
        k2=k2,
        annual_tax_normal=annual_normal,
        annual_tax=annual,
        mtd_normal=mtd_normal,
        mtd_additional=mtd_additional,
        mtd=mtd_normal + mtd_additional,
    )


@dataclass
class MonthRow:
    month: int
    name: str
    salary: Decimal
    additional: Decimal
    chargeable_projected: Decimal
    pcb_normal: Decimal
    pcb_additional: Decimal
    pcb: Decimal
    included_in_total: bool


@dataclass
class EstimateInput:
    resident: bool = True
    category: int = 1
    disabled_self: bool = False
    disabled_spouse: bool = False
    children_under_18: int = 0
    children_higher: int = 0
    children_disabled: int = 0
    children_disabled_higher: int = 0
    monthly_salary: Decimal = Decimal("0")
    monthly_allowance: Decimal = Decimal("0")
    monthly_epf: Decimal = Decimal("0")
    bonus: Decimal = Decimal("0")
    bonus_epf: Decimal = Decimal("0")
    bonus_month: int = 12
    other_income: Decimal = Decimal("0")
    start_month: int = 1
    as_of_month: int = 10
    prev_gross: Decimal = Decimal("0")
    prev_epf: Decimal = Decimal("0")
    prev_pcb: Decimal = Decimal("0")
    prev_reliefs: Decimal = Decimal("0")
    actual_pcb_before: Decimal | None = None
    zakat: Decimal = Decimal("0")
    zakat_via_payroll: bool = False
    tp1_submitted: bool = False
    socso_in_pcb: bool = True
    claims: Claims = field(default_factory=Claims)


@dataclass
class EstimateResult:
    resident: bool
    annual_income: Decimal
    income_lines: list[tuple[str, Decimal]]
    relief_lines: list[tuple[str, Decimal]]
    total_reliefs: Decimal
    chargeable: Decimal
    band: str
    tax_before_rebate: Decimal
    rebate: Decimal
    tax_after_rebate: Decimal
    zakat_rebate: Decimal
    tax_payable: Decimal
    pcb_to_lhdn: Decimal
    pcb_ytd_before: Decimal
    pcb_this_month: Decimal
    pcb_still_to_deduct: Decimal
    balance: Decimal
    position: str
    months: list[MonthRow]
    notes: list[str]
    as_of_month: int


def _money_list_total(lines: list[tuple[str, Decimal]]) -> Decimal:
    return sum((amount for _, amount in lines), Decimal("0.00"))


def estimate(data: EstimateInput) -> EstimateResult:
    notes: list[str] = []
    start = min(max(data.start_month, 1), 12)
    as_of = min(max(data.as_of_month, start), 12)
    months_worked = 13 - start
    y1 = trunc2(data.monthly_salary + data.monthly_allowance)
    children = child_relief_amount(
        data.children_under_18,
        data.children_higher,
        data.children_disabled,
        data.children_disabled_higher,
    )
    fixed, auto_lines = fixed_deductions(
        data.category, data.disabled_self, data.disabled_spouse, children
    )

    bonus_applies = data.bonus > 0 and data.bonus_month >= start
    if data.bonus > 0 and data.bonus_month < start:
        notes.append(
            "The bonus month is before you joined this employer, so it is not added again. Include that bonus in previous-employer income if it was paid this year."
        )

    employment = trunc2(y1 * Decimal(months_worked))
    bonus = data.bonus if bonus_applies else Decimal("0")
    income_lines = [("Employment income this employer", employment)]
    if bonus > 0:
        income_lines.append(("Bonus or other additional pay", bonus))
    if data.prev_gross > 0:
        income_lines.append(("Previous employer this year", data.prev_gross))
    if data.other_income > 0:
        income_lines.append(("Other taxable income", data.other_income))
    annual_income = _money_list_total(income_lines)

    mandatory_epf = trunc2(data.monthly_epf * Decimal(months_worked))
    if bonus_applies:
        mandatory_epf += data.bonus_epf
    mandatory_epf += data.prev_epf

    if not data.resident:
        tax_before = trunc2(annual_income * NON_RESIDENT_RATE)
        # Non-residents do not get resident reliefs or the RM400 rebate.
        pcb_rows: list[MonthRow] = []
        pcb_total = Decimal("0")
        pcb_before = data.actual_pcb_before if data.actual_pcb_before is not None else Decimal("0")
        pcb_this = Decimal("0")
        running_before = Decimal("0")
        for month in range(start, 13):
            pay = y1
            extra = bonus if month == data.bonus_month and bonus_applies else Decimal("0")
            raw = trunc2((pay + extra) * NON_RESIDENT_RATE)
            mtd = finalize_mtd(raw)
            included = data.actual_pcb_before is None or month >= as_of
            if data.actual_pcb_before is None and month < as_of:
                running_before += mtd
            if month == as_of:
                pcb_this = mtd
            if included and data.actual_pcb_before is None:
                pcb_total += mtd
            elif included and month >= as_of:
                pcb_total += mtd
            pcb_rows.append(
                MonthRow(month, MONTH_NAMES[month - 1], pay, extra, annual_income, mtd, Decimal("0"), mtd, included)
            )
        if data.actual_pcb_before is None:
            pcb_before = running_before
            pcb_to_lhdn = pcb_total
        else:
            pcb_to_lhdn = data.actual_pcb_before + sum(
                (row.pcb for row in pcb_rows if row.month >= as_of), Decimal("0")
            )
        still = sum((row.pcb for row in pcb_rows if row.month >= as_of), Decimal("0"))
        balance = pcb_to_lhdn - tax_before
        notes.append(
            "Non-resident PCB is 30% of remuneration. Resident reliefs and the personal rebate are not applied."
        )
        return EstimateResult(
            resident=False,
            annual_income=annual_income,
            income_lines=income_lines,
            relief_lines=[],
            total_reliefs=Decimal("0"),
            chargeable=annual_income,
            band="Flat 30% non-resident rate",
            tax_before_rebate=tax_before,
            rebate=Decimal("0"),
            tax_after_rebate=tax_before,
            zakat_rebate=Decimal("0"),
            tax_payable=tax_before,
            pcb_to_lhdn=pcb_to_lhdn,
            pcb_ytd_before=pcb_before,
            pcb_this_month=pcb_this,
            pcb_still_to_deduct=still,
            balance=balance,
            position="refund" if balance > 0 else "payable" if balance < 0 else "settled",
            months=pcb_rows,
            notes=notes,
            as_of_month=as_of,
        )

    reliefs = apply_claims(data.claims, data.category, mandatory_epf, auto_lines, fixed)
    notes.extend(reliefs.notes)
    if data.disabled_spouse and data.category == 1:
        notes.append("Disabled-spouse relief is left out because the single category has no spouse relief.")

    chargeable = trunc2(annual_income - reliefs.total)
    if chargeable < 0:
        chargeable = Decimal("0.00")

    tax_before = statutory_tax(chargeable)
    rebate = min(personal_rebate(chargeable, data.category), tax_before)
    tax_after = tax_before - rebate
    zakat = max(D(data.zakat), Decimal("0"))
    zakat_rebate = min(zakat, tax_after)
    if zakat > tax_after and zakat > 0:
        notes.append("Zakat rebate cannot be more than the tax after the personal rebate.")
    tax_payable = tax_after - zakat_rebate

    lp_for_pcb = data.prev_reliefs
    if data.socso_in_pcb:
        lp_for_pcb += reliefs.socso
    if data.tp1_submitted:
        lp_for_pcb += reliefs.optional_for_tp1
    elif reliefs.optional_for_tp1 > 0:
        notes.append(
            "Extra reliefs are counted in your year-end tax only. PCB ignores them until your employer has a TP1 for them, which is why a refund builds up."
        )

    y_acc = data.prev_gross
    k_acc = min(data.prev_epf, EPF_CAP)
    x_acc = data.prev_pcb
    lp_acc = Decimal("0")
    rows: list[MonthRow] = []
    simulated_before = data.prev_pcb

    for month in range(start, 13):
        if data.actual_pcb_before is not None and month == as_of:
            x_acc = data.actual_pcb_before
        months_after = 12 - month
        is_bonus_month = bonus_applies and month == data.bonus_month
        yt = bonus if is_bonus_month else Decimal("0")
        epf_t = data.bonus_epf if is_bonus_month else Decimal("0")
        lp1 = lp_for_pcb if month == start else Decimal("0")
        result = compute_month(
            y_acc=y_acc,
            k_acc=k_acc,
            x_acc=x_acc,
            z_acc=Decimal("0"),
            lp_acc=lp_acc,
            y1=y1,
            epf_month=data.monthly_epf,
            yt=yt,
            epf_additional=epf_t,
            lp1=lp1,
            months_after=months_after,
            category=data.category,
            fixed=fixed,
        )
        included = not (data.actual_pcb_before is not None and month < as_of)
        if month < as_of and data.actual_pcb_before is None:
            simulated_before += result.mtd
        rows.append(
            MonthRow(
                month=month,
                name=MONTH_NAMES[month - 1],
                salary=y1,
                additional=yt,
                chargeable_projected=result.p,
                pcb_normal=result.mtd_normal,
                pcb_additional=result.mtd_additional,
                pcb=result.mtd,
                included_in_total=included,
            )
        )
        y_acc = trunc2(y_acc + y1 + yt)
        k_acc = trunc2(k_acc + result.k1 + result.kt)
        x_acc = trunc2(x_acc + result.mtd)
        lp_acc = trunc2(lp_acc + lp1)

    if data.actual_pcb_before is None:
        pcb_before = simulated_before
    else:
        pcb_before = data.actual_pcb_before
        notes.append(
            "PCB already deducted is taken from the figure you entered. Later months are still projected from a steady salary."
        )

    still = sum((row.pcb for row in rows if row.month >= as_of), Decimal("0"))
    pcb_this = next((row.pcb for row in rows if row.month == as_of), Decimal("0"))
    pcb_total = pcb_before + still
    if data.zakat_via_payroll and zakat > 0:
        pcb_to_lhdn = pcb_total - zakat
        if pcb_to_lhdn < 0:
            pcb_to_lhdn = Decimal("0.00")
        notes.append(
            "Zakat deducted through payroll is treated as paid to the zakat authority, not to LHDN, and it still rebates the tax."
        )
    else:
        pcb_to_lhdn = pcb_total

    balance = pcb_to_lhdn - tax_payable
    if balance > 0:
        position = "refund"
    elif balance < 0:
        position = "payable"
    else:
        position = "settled"

    notes.append(
        "Salary is assumed to stay the same for every remaining month. A raise, unpaid leave, or a second bonus will move both PCB and the final tax."
    )
    if data.other_income > 0:
        notes.append("Other income is taxed at year end. It is not included in monthly PCB, so it can leave a balance to pay.")

    return EstimateResult(
        resident=True,
        annual_income=annual_income,
        income_lines=income_lines,
        relief_lines=reliefs.lines,
        total_reliefs=reliefs.total,
        chargeable=chargeable,
        band=band_label(chargeable),
        tax_before_rebate=tax_before,
        rebate=rebate,
        tax_after_rebate=tax_after,
        zakat_rebate=zakat_rebate,
        tax_payable=tax_payable,
        pcb_to_lhdn=pcb_to_lhdn,
        pcb_ytd_before=pcb_before,
        pcb_this_month=pcb_this,
        pcb_still_to_deduct=still,
        balance=balance,
        position=position,
        months=rows,
        notes=notes,
        as_of_month=as_of,
    )

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tax_engine import (  # noqa: E402
    Claims,
    EstimateInput,
    compute_month,
    epf_and_life_relief,
    estimate,
    round_up_5sen,
    trunc2,
)


class RoundingTests(unittest.TestCase):
    def test_truncate_drops_the_third_decimal(self):
        self.assertEqual(trunc2(Decimal("123.4534")), Decimal("123.45"))
        self.assertEqual(trunc2(Decimal("720.0042")), Decimal("720.00"))

    def test_mtd_rounds_up_to_the_next_five_sen(self):
        self.assertEqual(round_up_5sen(Decimal("287.02")), Decimal("287.05"))
        self.assertEqual(round_up_5sen(Decimal("152.06")), Decimal("152.10"))
        self.assertEqual(round_up_5sen(Decimal("207.50")), Decimal("207.50"))


class OfficialExampleTests(unittest.TestCase):
    """Worked example in the 2026 MTD specification, Exhibit 5."""

    def test_january_to_april_with_bonus(self):
        january = compute_month(
            y_acc=Decimal("0"),
            k_acc=Decimal("0"),
            x_acc=Decimal("0"),
            z_acc=Decimal("0"),
            lp_acc=Decimal("0"),
            y1=Decimal("5500"),
            epf_month=Decimal("605"),
            yt=Decimal("0"),
            epf_additional=Decimal("0"),
            lp1=Decimal("0"),
            months_after=11,
            category=3,
            fixed=Decimal("15000"),
        )
        self.assertEqual(january.p, Decimal("47000.07"))
        self.assertEqual(january.mtd, Decimal("110.00"))

        february = compute_month(
            y_acc=Decimal("5500"),
            k_acc=Decimal("605"),
            x_acc=Decimal("110.00"),
            z_acc=Decimal("0"),
            lp_acc=Decimal("0"),
            y1=Decimal("5500"),
            epf_month=Decimal("605"),
            yt=Decimal("0"),
            epf_additional=Decimal("0"),
            lp1=Decimal("0"),
            months_after=10,
            category=3,
            fixed=Decimal("15000"),
        )
        self.assertEqual(february.p, Decimal("47000.00"))
        self.assertEqual(february.mtd, Decimal("110.00"))

        march = compute_month(
            y_acc=Decimal("11000"),
            k_acc=Decimal("1210"),
            x_acc=Decimal("220.00"),
            z_acc=Decimal("0"),
            lp_acc=Decimal("0"),
            y1=Decimal("5500"),
            epf_month=Decimal("605"),
            yt=Decimal("0"),
            epf_additional=Decimal("0"),
            lp1=Decimal("300"),
            months_after=9,
            category=3,
            fixed=Decimal("15000"),
        )
        self.assertEqual(march.p, Decimal("46700.07"))
        self.assertEqual(march.mtd, Decimal("108.20"))

        april = compute_month(
            y_acc=Decimal("16500"),
            k_acc=Decimal("1815"),
            x_acc=Decimal("328.20"),
            z_acc=Decimal("0"),
            lp_acc=Decimal("300"),
            y1=Decimal("5500"),
            epf_month=Decimal("605"),
            yt=Decimal("8250"),
            epf_additional=Decimal("908"),
            lp1=Decimal("300"),
            months_after=8,
            category=3,
            fixed=Decimal("15000"),
        )
        self.assertEqual(april.p_normal, Decimal("46400.00"))
        self.assertEqual(april.mtd_normal, Decimal("106.20"))
        self.assertEqual(april.p, Decimal("54650.00"))
        self.assertEqual(april.annual_tax, Decimal("2011.50"))
        self.assertEqual(april.mtd_additional, Decimal("727.50"))
        self.assertEqual(april.mtd, Decimal("833.70"))


class PublishedJanuaryCaseTests(unittest.TestCase):
    def test_single_salary_6000_in_january(self):
        result = compute_month(
            y_acc=Decimal("0"),
            k_acc=Decimal("0"),
            x_acc=Decimal("0"),
            z_acc=Decimal("0"),
            lp_acc=Decimal("0"),
            y1=Decimal("6000"),
            epf_month=Decimal("660"),
            yt=Decimal("0"),
            epf_additional=Decimal("0"),
            lp1=Decimal("0"),
            months_after=11,
            category=1,
            fixed=Decimal("9000"),
        )
        self.assertEqual(result.p, Decimal("59000.07"))
        self.assertEqual(result.mtd, Decimal("207.50"))


class EpfLifeTests(unittest.TestCase):
    def test_mandatory_epf_caps_at_4000_and_life_stays_separate(self):
        epf, life = epf_and_life_relief(Decimal("7920"), Decimal("1000"), Decimal("3000"))
        self.assertEqual(epf, Decimal("4000"))
        self.assertEqual(life, Decimal("3000"))

    def test_voluntary_only_can_use_both_buckets(self):
        epf, life = epf_and_life_relief(Decimal("0"), Decimal("7000"), Decimal("0"))
        self.assertEqual(epf, Decimal("4000"))
        self.assertEqual(life, Decimal("3000"))


class RefundTests(unittest.TestCase):
    def test_matching_reliefs_leave_no_refund(self):
        result = estimate(
            EstimateInput(
                monthly_salary=Decimal("6000"),
                monthly_epf=Decimal("660"),
                as_of_month=1,
            )
        )
        self.assertEqual(result.tax_payable, Decimal("2490.00"))
        self.assertEqual(result.pcb_to_lhdn, Decimal("2490.00"))
        self.assertEqual(result.balance, Decimal("0.00"))
        self.assertEqual(result.position, "settled")
        self.assertEqual(result.months[0].pcb, Decimal("207.50"))

    def test_lifestyle_relief_claimed_only_at_filing_creates_a_refund(self):
        result = estimate(
            EstimateInput(
                monthly_salary=Decimal("6000"),
                monthly_epf=Decimal("660"),
                claims=Claims(lifestyle=Decimal("2500")),
                tp1_submitted=False,
            )
        )
        self.assertEqual(result.chargeable, Decimal("56500.00"))
        self.assertEqual(result.tax_payable, Decimal("2215.00"))
        self.assertEqual(result.pcb_to_lhdn, Decimal("2490.00"))
        self.assertEqual(result.balance, Decimal("275.00"))
        self.assertEqual(result.position, "refund")

    def test_tp1_reliefs_reduce_pcb_as_well_as_the_final_tax(self):
        result = estimate(
            EstimateInput(
                monthly_salary=Decimal("6000"),
                monthly_epf=Decimal("660"),
                claims=Claims(
                    lifestyle=Decimal("2500"),
                    life_insurance=Decimal("3000"),
                    socso=Decimal("350"),
                ),
                tp1_submitted=True,
                socso_in_pcb=True,
            )
        )
        self.assertEqual(result.tax_payable, Decimal("1846.50"))
        self.assertEqual(result.pcb_to_lhdn, result.tax_payable)
        self.assertEqual(result.balance, Decimal("0.00"))

    def test_other_income_can_leave_tax_to_pay(self):
        result = estimate(
            EstimateInput(
                monthly_salary=Decimal("6000"),
                monthly_epf=Decimal("660"),
                other_income=Decimal("12000"),
            )
        )
        self.assertEqual(result.position, "payable")
        self.assertLess(result.balance, 0)

    def test_low_income_rebate_wipes_out_the_tax(self):
        result = estimate(
            EstimateInput(
                monthly_salary=Decimal("2000"),
                monthly_epf=Decimal("220"),
            )
        )
        self.assertEqual(result.tax_payable, Decimal("0.00"))
        self.assertEqual(result.pcb_to_lhdn, Decimal("0.00"))
        self.assertGreater(result.rebate, 0)

    def test_non_resident_is_thirty_percent(self):
        result = estimate(
            EstimateInput(
                resident=False,
                monthly_salary=Decimal("3000"),
                as_of_month=1,
            )
        )
        self.assertEqual(result.months[0].pcb, Decimal("900.00"))
        self.assertEqual(result.tax_payable, Decimal("10800.00"))
        self.assertEqual(result.relief_lines, [])


if __name__ == "__main__":
    unittest.main()

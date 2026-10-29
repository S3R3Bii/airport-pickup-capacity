import sys, unittest
from datetime import date, timedelta
from fractions import Fraction as Q
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from model import empirical, history, predict, scenario, tie_key


class PolicyFixtures(unittest.TestCase):
    def test_median_lower_endpoint(self):
        self.assertEqual(empirical([9, 1, 3, 7], Q(1, 2)), (3, 2))

    def test_upper_rank(self):
        self.assertEqual(empirical([9, 1, 3, 7], Q(3, 4)), (7, 3))

    def test_high_rank(self):
        self.assertEqual(empirical([9, 1, 3, 7], Q(9, 10)), (9, 4))

    def test_ties(self):
        self.assertEqual(empirical([2, 2, 2, 2], Q(3, 4)), (2, 3))

    def test_cap(self):
        self.assertEqual(scenario(300, 400, 250, 3), (250, 50, 0, 150))

    def test_excess(self):
        self.assertEqual(scenario(30, 40, 250, 3), (40, 0, 10, 10))

    def test_zero(self):
        self.assertEqual(scenario(0, 0, 100, 9), (0, 0, 0, 0))

    def test_past_only(self):
        d = date(2024, 8, 5)
        data = {(d - timedelta(days=i), 132, 12): i for i in range(-1, 30)}
        h = history(data, d, 132, 12, 28, "weekday_hour")
        self.assertEqual([n for dd, n in h], [28, 21, 14, 7])
        self.assertTrue(all(dd < d for dd, n in h))

    def test_daytype(self):
        d = date(2024, 8, 5)
        data = {(d - timedelta(days=i), 132, 12): i for i in range(1, 8)}
        self.assertEqual(len(history(data, d, 132, 12, 7, "daytype_hour")), 5)

    def test_insufficient(self):
        self.assertEqual(
            predict(
                {},
                date(2024, 8, 5),
                132,
                12,
                dict(id="x", window=28, group="weekday_hour", q="1/2"),
            )[2],
            "INSUFFICIENT_HISTORY",
        )

    def test_baseline_fallback(self):
        d = date(2024, 11, 10)
        data = {(date(2024, 10, 27), 132, 1): 8}
        self.assertEqual(
            predict(data, d, 132, 1, dict(id="previous_available_week"))[0], 8
        )

    def test_tie_order(self):
        a = dict(group="daytype_hour", window=28, q="1/2")
        b = dict(group="weekday_hour", window=28, q="1/2")
        self.assertLess(tie_key(a, 10), tie_key(b, 10))


if __name__ == "__main__":
    unittest.main()

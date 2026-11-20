import unittest

from points import Order, earned, order_points, points_for


class PointsForTest(unittest.TestCase):
    def test_whole_euros_times_tier_rate(self):
        self.assertEqual(points_for(42.5, "basic"), 42)
        self.assertEqual(points_for(42.5, "gold"), 126)

    def test_bonus_only_above_100(self):
        self.assertEqual(points_for(100, "silver"), 200)
        self.assertEqual(points_for(100.01, "silver"), 250)

    def test_unknown_tier(self):
        with self.assertRaises(ValueError):
            points_for(10, "platinum")


class OrderPointsTest(unittest.TestCase):
    def test_promo_doubles_the_rate(self):
        self.assertEqual(order_points(Order(4250, "silver")), 84)
        self.assertEqual(order_points(Order(4250, "silver", promo=True)), 168)

    def test_bonus_is_not_doubled(self):
        self.assertEqual(order_points(Order(20000, "basic", promo=True)), 450)


class EarnedTest(unittest.TestCase):
    def test_earned_matches_points_for(self):
        self.assertEqual(earned(77.7, "gold"), points_for(77.7, "gold"))


if __name__ == "__main__":
    unittest.main()

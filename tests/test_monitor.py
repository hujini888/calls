import unittest

from zvonki.models import PairSnapshot, Watch
from zvonki.monitor import PriceTracker


def watch():
    return Watch(
        id=1,
        chat_id=10,
        chain_id="base",
        token_address="0xABC",
        pair_address="pool",
        symbol="MEME",
        quote_symbol="WETH",
        dex_id="uniswap",
        threshold_percent=10,
        window_seconds=30,
        min_liquidity_usd=5000,
        cooldown_seconds=600,
    )


def snapshot(price, liquidity=10000):
    return PairSnapshot(
        chain_id="base",
        token_address="0xABC",
        pair_address="pool",
        dex_id="uniswap",
        symbol="MEME",
        quote_symbol="WETH",
        price_usd=price,
        liquidity_usd=liquidity,
        market_cap=100000,
        fdv=100000,
        volume_m5=2000,
        buys_m5=10,
        sells_m5=5,
        pair_created_at_ms=None,
        url="https://example.test",
    )


class PriceTrackerTests(unittest.TestCase):
    def test_alerts_after_full_window(self):
        tracker = PriceTracker()
        self.assertIsNone(tracker.evaluate(watch(), snapshot(1.0), 1000))
        alert = tracker.evaluate(watch(), snapshot(1.11), 1030)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.direction, "up")
        self.assertAlmostEqual(alert.change_percent, 11.0)

    def test_does_not_repeat_while_threshold_stays_crossed(self):
        tracker = PriceTracker()
        tracker.evaluate(watch(), snapshot(1.0), 1000)
        self.assertIsNotNone(tracker.evaluate(watch(), snapshot(1.11), 1030))
        self.assertIsNone(tracker.evaluate(watch(), snapshot(1.20), 1060))

    def test_liquidity_filter(self):
        tracker = PriceTracker()
        tracker.evaluate(watch(), snapshot(1.0), 1000)
        self.assertIsNone(tracker.evaluate(watch(), snapshot(1.20, 100), 1030))

    def test_down_alert(self):
        tracker = PriceTracker()
        tracker.evaluate(watch(), snapshot(1.0), 1000)
        alert = tracker.evaluate(watch(), snapshot(0.89), 1030)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.direction, "down")


if __name__ == "__main__":
    unittest.main()


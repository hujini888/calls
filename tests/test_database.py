import unittest
from pathlib import Path

from zvonki.database import Database
from zvonki.models import PairSnapshot


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(Path(":memory:"))
        self.snapshot = PairSnapshot(
            chain_id="base",
            token_address="0xABC",
            pair_address="pool",
            dex_id="uniswap",
            symbol="MEME",
            quote_symbol="WETH",
            price_usd=1,
            liquidity_usd=10000,
            market_cap=None,
            fdv=100000,
            volume_m5=1000,
            buys_m5=1,
            sells_m5=2,
            pair_created_at_ms=None,
            url="https://example.test",
        )

    def tearDown(self):
        self.db.close()

    def test_upsert_and_ownership(self):
        first = self.db.add_watch(1, self.snapshot, 10, 30, 5000, 600)
        updated = self.db.add_watch(1, self.snapshot, 15, 60, 7000, 900)
        self.assertEqual(first.id, updated.id)
        self.assertEqual(updated.threshold_percent, 15)
        self.assertIsNone(self.db.get_watch(2, first.id))
        self.assertFalse(self.db.delete_watch(2, first.id))
        self.assertTrue(self.db.delete_watch(1, first.id))


if __name__ == "__main__":
    unittest.main()


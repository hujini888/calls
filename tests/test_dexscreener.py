import unittest

from zvonki.dexscreener import select_pair


def pair(address, liquidity, price="0.01", base="0xABC"):
    return {
        "chainId": "base",
        "dexId": "uniswap",
        "pairAddress": address,
        "baseToken": {"address": base, "symbol": "MEME"},
        "quoteToken": {"address": "0xUSDC", "symbol": "USDC"},
        "priceUsd": price,
        "liquidity": {"usd": liquidity},
        "volume": {"m5": 1234},
        "txns": {"m5": {"buys": 12, "sells": 4}},
        "url": "https://dexscreener.com/base/example",
    }


class PairSelectionTests(unittest.TestCase):
    def test_selects_most_liquid_pair(self):
        result = select_pair([pair("small", 100), pair("large", 5000)], "0xabc")
        self.assertIsNotNone(result)
        self.assertEqual(result.pair_address, "large")
        self.assertEqual(result.price_usd, 0.01)

    def test_respects_pinned_pair(self):
        result = select_pair(
            [pair("small", 100), pair("large", 5000)], "0xABC", "small"
        )
        self.assertEqual(result.pair_address, "small")

    def test_rejects_quote_token(self):
        result = select_pair([pair("x", 5000, base="0xOTHER")], "0xABC")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()


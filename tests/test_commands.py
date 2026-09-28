import unittest

from zvonki.commands import UserInputError, parse_add, parse_duration


class DurationTests(unittest.TestCase):
    def test_units(self):
        self.assertEqual(parse_duration("30s"), 30)
        self.assertEqual(parse_duration("5m"), 300)
        self.assertEqual(parse_duration("2h"), 7200)

    def test_invalid_duration(self):
        with self.assertRaises(UserInputError):
            parse_duration("later")


class AddCommandTests(unittest.TestCase):
    def test_full_command(self):
        command = parse_add(
            "/add base 0xABC 12.5% 30s $10,000 15m",
            default_min_liquidity=5000,
            default_cooldown=600,
        )
        self.assertEqual(command.chain_id, "base")
        self.assertEqual(command.token_address, "0xABC")
        self.assertEqual(command.threshold_percent, 12.5)
        self.assertEqual(command.window_seconds, 30)
        self.assertEqual(command.min_liquidity_usd, 10000)
        self.assertEqual(command.cooldown_seconds, 900)

    def test_defaults(self):
        command = parse_add("/add solana AbCd 10 1m", 4000, 500)
        self.assertEqual(command.min_liquidity_usd, 4000)
        self.assertEqual(command.cooldown_seconds, 500)

    def test_chain_alias(self):
        command = parse_add("/add eth 0xABC 10 1m", 4000, 500)
        self.assertEqual(command.chain_id, "ethereum")

    def test_robinhood_aliases(self):
        for alias in ("robinhood", "hood", "rh"):
            command = parse_add(f"/add {alias} 0xABC 10 1m", 4000, 500)
            self.assertEqual(command.chain_id, "robinhood")

    def test_window_too_short(self):
        with self.assertRaises(UserInputError):
            parse_add("/add solana AbCd 10 2s", 4000, 500)


if __name__ == "__main__":
    unittest.main()

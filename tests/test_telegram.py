import unittest

from zvonki.telegram import TelegramClient


class FakeHttp:
    async def request_json(self, url, data=None, timeout=15, retries=2):
        self.url = url
        return {"ok": True, "result": {"username": "zvonki_test_bot"}}


class TelegramClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_me_validates_bot(self):
        http = FakeHttp()
        result = await TelegramClient("test-token", http).get_me()
        self.assertEqual(result["username"], "zvonki_test_bot")
        self.assertTrue(http.url.endswith("/getMe"))


if __name__ == "__main__":
    unittest.main()


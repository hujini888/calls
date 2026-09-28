import asyncio
import logging

from .commands import (
    UserInputError,
    command_name,
    format_duration,
    parse_add,
    parse_watch_id,
)
from .config import Config
from .database import Database
from .dexscreener import DexScreenerClient
from .http import JsonHttpClient
from .monitor import Monitor
from .telegram import TelegramClient


logger = logging.getLogger(__name__)

HELP = """🔔 Звонки — монитор движений токенов на DEX

/add <chain> <CA> <процент> <период> [мин. ликвидность] [cooldown]
Добавить или обновить токен.

Пример:
/add solana 7xKX...pump 10 30s 5000 10m
/add ethereum 0x123...abc 7.5 1m 20000 15m
/add robinhood 0x123...abc 10 30s 5000 10m

/list — список мониторинга
/pause <id> — приостановить
/resume <id> — возобновить
/refresh <id> — выбрать заново самый ликвидный пул
/delete <id> — удалить
/status — состояние сервиса
/whoami — показать Telegram chat ID

Периоды: 30s, 5m, 1h. Процент работает в обе стороны: рост и падение."""


class Application:
    def __init__(self, config: Config):
        self.config = config
        self.http = JsonHttpClient()
        self.database = Database(config.database_path)
        self.dex = DexScreenerClient(self.http)
        self.telegram = TelegramClient(config.telegram_bot_token, self.http)
        self.monitor = Monitor(
            self.database, self.dex, self.telegram, config.poll_interval_seconds
        )
        self.update_offset = 0

    def _allowed(self, chat_id: int) -> bool:
        return not self.config.allowed_chat_ids or chat_id in self.config.allowed_chat_ids

    async def _handle_add(self, chat_id: int, text: str) -> None:
        command = parse_add(
            text,
            self.config.default_min_liquidity_usd,
            self.config.default_cooldown_seconds,
        )
        snapshot = await self.dex.resolve_token(command.chain_id, command.token_address)
        if not snapshot:
            raise UserInputError(
                "Не нашёл пул с USD-ценой. Проверь chain ID и адрес контракта."
            )
        watch = self.database.add_watch(
            chat_id,
            snapshot,
            command.threshold_percent,
            command.window_seconds,
            command.min_liquidity_usd,
            command.cooldown_seconds,
        )
        self.monitor.tracker.clear(watch.id)
        await self.telegram.send_message(
            chat_id,
            f"✅ Добавлено: #{watch.id} {watch.symbol}/{watch.quote_symbol}\n"
            f"Сеть: {watch.chain_id} · DEX: {watch.dex_id}\n"
            f"Порог: ±{watch.threshold_percent:g}% за {format_duration(watch.window_seconds)}\n"
            f"Мин. ликвидность: ${watch.min_liquidity_usd:,.0f}\n"
            f"Cooldown: {format_duration(watch.cooldown_seconds)}\n"
            f"Пул: {watch.pair_address}",
        )

    async def _handle_list(self, chat_id: int) -> None:
        watches = self.database.list_watches(chat_id)
        if not watches:
            await self.telegram.send_message(chat_id, "Список пуст. Добавь токен командой /add")
            return
        lines = ["📋 Мониторинг:"]
        for watch in watches:
            state = "🟢" if watch.enabled else "⏸"
            lines.append(
                f"\n{state} #{watch.id} {watch.symbol}/{watch.quote_symbol} · {watch.chain_id}\n"
                f"±{watch.threshold_percent:g}% / {format_duration(watch.window_seconds)} · "
                f"ликв. от ${watch.min_liquidity_usd:,.0f}"
            )
        await self.telegram.send_message(chat_id, "".join(lines))

    async def _handle_toggle(self, chat_id: int, text: str, enabled: bool) -> None:
        name = "resume" if enabled else "pause"
        watch_id = parse_watch_id(text, name)
        if not self.database.set_enabled(chat_id, watch_id, enabled):
            raise UserInputError("Правило с таким ID не найдено")
        self.monitor.tracker.clear(watch_id)
        await self.telegram.send_message(
            chat_id, "▶️ Мониторинг включён" if enabled else "⏸ Мониторинг приостановлен"
        )

    async def _handle_delete(self, chat_id: int, text: str) -> None:
        watch_id = parse_watch_id(text, "delete")
        if not self.database.delete_watch(chat_id, watch_id):
            raise UserInputError("Правило с таким ID не найдено")
        self.monitor.tracker.clear(watch_id)
        await self.telegram.send_message(chat_id, f"🗑 Правило #{watch_id} удалено")

    async def _handle_refresh(self, chat_id: int, text: str) -> None:
        watch_id = parse_watch_id(text, "refresh")
        watch = self.database.get_watch(chat_id, watch_id)
        if not watch:
            raise UserInputError("Правило с таким ID не найдено")
        snapshot = await self.dex.resolve_token(watch.chain_id, watch.token_address)
        if not snapshot:
            raise UserInputError("Не нашёл подходящий пул")
        self.database.update_pair(watch.id, snapshot)
        self.monitor.tracker.clear(watch.id)
        await self.telegram.send_message(
            chat_id,
            f"🔄 Пул обновлён: {snapshot.symbol}/{snapshot.quote_symbol}\n"
            f"DEX: {snapshot.dex_id}\nПул: {snapshot.pair_address}",
        )

    async def handle_text(self, chat_id: int, text: str) -> None:
        if not self._allowed(chat_id):
            logger.warning("Rejected Telegram chat_id=%s", chat_id)
            return
        name = command_name(text)
        try:
            if name in ("/start", "/help"):
                await self.telegram.send_message(chat_id, HELP)
            elif name == "/add":
                await self._handle_add(chat_id, text)
            elif name == "/list":
                await self._handle_list(chat_id)
            elif name == "/pause":
                await self._handle_toggle(chat_id, text, False)
            elif name == "/resume":
                await self._handle_toggle(chat_id, text, True)
            elif name == "/delete":
                await self._handle_delete(chat_id, text)
            elif name == "/refresh":
                await self._handle_refresh(chat_id, text)
            elif name == "/status":
                active = len(self.database.list_watches(chat_id, enabled_only=True))
                total = len(self.database.list_watches(chat_id))
                await self.telegram.send_message(
                    chat_id,
                    f"✅ Сервис работает\nАктивно: {active} из {total}\n"
                    f"Опрос DexScreener: каждые {self.config.poll_interval_seconds:g} сек.",
                )
            elif name == "/whoami":
                await self.telegram.send_message(chat_id, f"Твой Telegram chat ID: {chat_id}")
            else:
                await self.telegram.send_message(chat_id, "Неизвестная команда. Нажми /help")
        except UserInputError as exc:
            await self.telegram.send_message(chat_id, f"⚠️ {exc}")
        except Exception:
            logger.exception("Command failed: %s", name)
            await self.telegram.send_message(
                chat_id, "⚠️ Не удалось выполнить команду. Попробуй ещё раз чуть позже."
            )

    async def bot_loop(self) -> None:
        while True:
            try:
                updates = await self.telegram.get_updates(self.update_offset)
                for update in updates:
                    self.update_offset = max(self.update_offset, int(update["update_id"]) + 1)
                    message = update.get("message") or {}
                    text = message.get("text")
                    chat = message.get("chat") or {}
                    if text and chat.get("id") is not None:
                        await self.handle_text(int(chat["id"]), text.strip())
            except Exception:
                logger.exception("Telegram polling failed")
                await asyncio.sleep(3)

    async def run(self) -> None:
        bot = await self.telegram.get_me()
        logger.info("Telegram bot connected: @%s", bot.get("username", "unknown"))
        await asyncio.gather(self.bot_loop(), self.monitor.run())


def main() -> None:
    try:
        config = Config.from_env()
    except ValueError as exc:
        raise SystemExit(f"Configuration error: {exc}")
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = Application(config)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Stopped")
    finally:
        app.database.close()

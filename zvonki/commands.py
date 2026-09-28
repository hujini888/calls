import shlex
from dataclasses import dataclass


class UserInputError(ValueError):
    pass


CHAIN_ALIASES = {
    "sol": "solana",
    "eth": "ethereum",
    "bnb": "bsc",
    "arb": "arbitrum",
    "avax": "avalanche",
    "matic": "polygon",
    "hood": "robinhood",
    "rh": "robinhood",
}


def parse_duration(value: str) -> int:
    value = value.strip().lower()
    if not value:
        raise UserInputError("Пустой период")
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    suffix = value[-1]
    if suffix in multipliers:
        number = value[:-1]
        multiplier = multipliers[suffix]
    else:
        number = value
        multiplier = 1
    try:
        seconds = int(number) * multiplier
    except ValueError as exc:
        raise UserInputError(f"Не понимаю период: {value}") from exc
    if seconds <= 0:
        raise UserInputError("Период должен быть больше нуля")
    return seconds


def format_duration(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


@dataclass(frozen=True)
class AddCommand:
    chain_id: str
    token_address: str
    threshold_percent: float
    window_seconds: int
    min_liquidity_usd: float
    cooldown_seconds: int


def command_name(text: str) -> str:
    try:
        first = shlex.split(text)[0]
    except (ValueError, IndexError):
        return ""
    return first.split("@", 1)[0].lower()


def parse_add(text: str, default_min_liquidity: float, default_cooldown: int) -> AddCommand:
    try:
        parts = shlex.split(text)
    except ValueError as exc:
        raise UserInputError("Не удалось разобрать команду") from exc
    if len(parts) < 5 or len(parts) > 7:
        raise UserInputError(
            "Формат: /add <chain> <CA> <процент> <период> [мин. ликвидность] [cooldown]"
        )
    raw_chain_id = parts[1].strip().lower()
    chain_id = CHAIN_ALIASES.get(raw_chain_id, raw_chain_id)
    token_address = parts[2].strip()
    if not chain_id or not token_address:
        raise UserInputError("Нужны сеть и адрес контракта")
    try:
        threshold = float(parts[3].rstrip("%"))
    except ValueError as exc:
        raise UserInputError("Процент должен быть числом") from exc
    if threshold <= 0 or threshold > 10000:
        raise UserInputError("Процент должен быть больше 0 и не больше 10000")

    window = parse_duration(parts[4])
    if window < 5 or window > 86400:
        raise UserInputError("Период должен быть от 5 секунд до 24 часов")

    min_liquidity = default_min_liquidity
    if len(parts) >= 6:
        try:
            min_liquidity = float(parts[5].replace("$", "").replace(",", ""))
        except ValueError as exc:
            raise UserInputError("Минимальная ликвидность должна быть числом") from exc
        if min_liquidity < 0:
            raise UserInputError("Минимальная ликвидность не может быть отрицательной")

    cooldown = default_cooldown if len(parts) < 7 else parse_duration(parts[6])
    return AddCommand(chain_id, token_address, threshold, window, min_liquidity, cooldown)


def parse_watch_id(text: str, command: str) -> int:
    parts = text.split()
    if len(parts) != 2:
        raise UserInputError(f"Формат: /{command} <id>")
    try:
        value = int(parts[1])
    except ValueError as exc:
        raise UserInputError("ID должен быть числом") from exc
    if value <= 0:
        raise UserInputError("ID должен быть больше нуля")
    return value

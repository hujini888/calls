# Звонки

Telegram-бот следит за токенами из разных блокчейнов через официальный API
DexScreener и сообщает, когда цена выросла или упала на заданный процент за
заданное время.

Проект не торгует и не запрашивает приватные ключи. Для мониторинга нужны только
chain ID и адрес контракта токена.

## Что умеет

- сети, которые поддерживает DexScreener: Robinhood Chain, Solana, Ethereum,
  Base, BSC и другие;
- автоматический выбор пула с наибольшей USD-ликвидностью;
- закрепление выбранного пула, чтобы переключение между пулами не создавало
  ложный сигнал;
- пакетная загрузка до 30 адресов одним запросом;
- собственные скользящие окна от 5 секунд до 24 часов;
- одинаковый порог для роста и падения;
- фильтр минимальной ликвидности;
- cooldown и повторное «взведение» сигнала после возврата движения ниже
  половины порога;
- SQLite для правил и состояния последних уведомлений;
- ограничение доступа к боту по Telegram chat ID.

## Быстрый запуск через Docker

1. Создайте бота через `@BotFather` и получите токен.
2. Скопируйте настройки:

   ```bash
   cp .env.example .env
   ```

3. Укажите `TELEGRAM_BOT_TOKEN` в `.env`. Для личного бота рекомендуется также
   заполнить `TELEGRAM_ALLOWED_CHAT_IDS`.
4. Запустите:

   ```bash
   docker compose up -d --build
   docker compose logs -f zvonki
   ```

База хранится в именованном Docker-volume `zvonki_data` и не пропадает после
перезапуска или пересборки контейнера.

## Запуск без Docker

Нужен Python 3.9 или новее. Сторонние Python-пакеты не используются.

```bash
cp .env.example .env
set -a
source .env
set +a
python3 -m zvonki
```

## Деплой GitHub → Railway

1. Создайте пустой GitHub-репозиторий и отправьте в него содержимое проекта:

   ```bash
   git init
   git add .
   git commit -m "Initial Zvonki bot"
   git branch -M main
   git remote add origin https://github.com/USERNAME/zvonki.git
   git push -u origin main
   ```

2. В Railway выберите **New Project → Deploy from GitHub repo** и подключите
   репозиторий. Railway автоматически найдёт корневой `Dockerfile`.
3. В сервисе откройте **Variables** и добавьте:

   ```text
   TELEGRAM_BOT_TOKEN=токен_от_BotFather
   TELEGRAM_ALLOWED_CHAT_IDS=ваш_chat_id
   DATABASE_PATH=/app/data/zvonki.sqlite3
   POLL_INTERVAL_SECONDS=2
   DEFAULT_MIN_LIQUIDITY_USD=5000
   DEFAULT_COOLDOWN_SECONDS=600
   RAILWAY_RUN_UID=0
   ```

   Если chat ID пока неизвестен, временно оставьте
   `TELEGRAM_ALLOWED_CHAT_IDS` пустым, вызовите `/whoami`, затем ограничьте
   доступ и сделайте redeploy.
4. Прикрепите к сервису Railway Volume с mount path `/app/data`. Без volume
   SQLite-база исчезнет при следующем redeploy. `RAILWAY_RUN_UID=0` нужен,
   потому что Railway монтирует volume от root.
5. Оставьте одну реплику. Несколько реплик с одним Telegram-ботом будут
   конкурировать за `getUpdates` и могут дублировать мониторинг.
6. Публичный домен и переменная `PORT` не нужны: бот работает как background
   worker через Telegram long polling.

После запуска в Deploy Logs должна появиться строка:

```text
Telegram bot connected: @имя_бота
```

Каждый новый push в подключённую ветку GitHub запустит новый deploy.

## Команды Telegram

Добавить или обновить токен:

```text
/add <chain> <CA> <процент> <период> [мин. ликвидность] [cooldown]
```

Примеры:

```text
/add solana 7xKX...pump 10 30s 5000 10m
/add ethereum 0x123...abc 7.5 1m 20000 15m
/add base 0x123...abc 15 20s
/add robinhood 0x123...abc 10 30s 5000 10m
```

Можно использовать короткие алиасы: `sol` → `solana`, `eth` → `ethereum`,
`bnb` → `bsc`, `arb` → `arbitrum`, `avax` → `avalanche`, `matic` → `polygon`,
`hood`/`rh` → `robinhood`.

Здесь `10 30s` означает: уведомить при росте на 10% или падении на 10% за
30 секунд. Если ликвидность не указана, используется значение из
`DEFAULT_MIN_LIQUIDITY_USD`.

Остальные команды:

```text
/list
/pause <id>
/resume <id>
/refresh <id>
/delete <id>
/status
/whoami
/help
```

Команда `/whoami` показывает chat ID, который можно затем записать в
`TELEGRAM_ALLOWED_CHAT_IDS`.

`/refresh` заново выбирает наиболее ликвидный пул. После добавления токена бот
ждёт один полный период правила, чтобы накопить историю цены.

## Как считается сигнал

Каждые `POLL_INTERVAL_SECONDS` секунд бот получает текущую цену выбранного пула.
Он сравнивает её с последней сохранённой ценой не позднее начала окна:

```text
изменение = (текущая цена / цена в начале окна - 1) × 100%
```

После уведомления направление блокируется. Оно снова активируется, когда
движение опустится ниже половины порога, и при этом соблюдается cooldown. Это
защищает от серии одинаковых сообщений на одном движении.

## Настройки

| Переменная | По умолчанию | Назначение |
|---|---:|---|
| `TELEGRAM_BOT_TOKEN` | — | Обязательный токен бота |
| `TELEGRAM_ALLOWED_CHAT_IDS` | пусто | Разрешённые chat ID через запятую |
| `DATABASE_PATH` | `data/zvonki.sqlite3` | Файл SQLite |
| `POLL_INTERVAL_SECONDS` | `2` | Частота опроса |
| `DEFAULT_MIN_LIQUIDITY_USD` | `5000` | Фильтр ликвидности |
| `DEFAULT_COOLDOWN_SECONDS` | `600` | Пауза между сигналами направления |
| `LOG_LEVEL` | `INFO` | Уровень логирования |

## Ограничения MVP

- DexScreener отдаёт HTTP API, поэтому краткий скачок между двумя опросами может
  быть пропущен.
- История цен хранится в памяти. После перезапуска сервису нужен один полный
  период правила для накопления нового окна.
- Выбирается пул, в котором отслеживаемый токен является `baseToken`. Это
  соответствует обычным мемкоин-парам и позволяет корректно использовать
  `priceUsd` DexScreener.
- Бот использует long polling Telegram, поэтому публичный HTTPS-домен не нужен.

## Тесты

```bash
python3 -m unittest discover -s tests -v
```

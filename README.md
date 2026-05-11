# profiru-orders-watcher

MVP-сервис для мониторинга публичных страниц Profi.ru с заказами, фильтрации подходящих заявок и отправки уведомлений в Telegram.

## Что делает

- Обходит список публичных URL из `config.yaml`.
- Может мониторить личный backoffice Profi.ru через Selenium и уже открытую сессию Chrome.
- Извлекает карточки заказов из HTML.
- Нормализует заказ в единую модель.
- Фильтрует по ключевым словам, стоп-словам, городу и бюджету.
- Дедуплицирует заказы через SQLite.
- Отправляет новые подходящие заказы в Telegram.
- Добавляет в Telegram-сообщение кнопку «Откликнуться».
- Запускается вручную, по cron или в Docker.

## Важное ограничение

Репозиторий не содержит:

- обхода капчи;
- автоматического логина в личный кабинет;
- хранения логина/пароля Profi.ru;
- подмены fingerprint / stealth-режимов;
- массового высокочастотного скрейпинга;
- автоматических откликов на заказы.

По умолчанию сервис работает только с публично доступными страницами и с умеренным rate limit.
Backoffice-режим предполагает, что вы сами авторизовались в браузере, а сервис только читает страницу
и присылает ссылку для ручного отклика.

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
cp config.example.yaml config.yaml
```

Заполните `.env`:

```bash
TELEGRAM_BOT_TOKEN=123456:ABC
TELEGRAM_CHAT_ID=123456789
```

Проверьте конфиг:

```bash
profiru-watch validate-config --config config.yaml
```

Однократный запуск:

```bash
profiru-watch run --config config.yaml
```

Запуск в цикле:

```bash
profiru-watch loop --config config.yaml --interval 300
```

## Деплой на Fly.io

В проекте есть `fly.toml` и `config.production.yaml`. Production-режим использует Selenium в
headless Chromium и хранит SQLite в volume `/data`.

Сначала войдите в Fly:

```bash
flyctl auth login
```

Если имя приложения в `fly.toml` занято, замените `app = "profiru-orders-watcher-denisdobro"` на
свободное имя. Затем создайте приложение и volume:

```bash
flyctl apps create profiru-orders-watcher-denisdobro
flyctl volumes create orders_data --size 1 --region ams
```

Создайте secrets:

```bash
flyctl secrets set TELEGRAM_BOT_TOKEN="..."
flyctl secrets set TELEGRAM_CHAT_ID="..."
```

Production-конфиг по умолчанию использует только публичные страницы Profi.ru без авторизации.
`PROFI_COOKIES_JSON` нужен только если вы осознанно включаете `kind: backoffice_selenium`.

Деплой:

```bash
flyctl deploy
```

Логи:

```bash
flyctl logs
```

## Backoffice-режим

В `config.yaml` можно включить источник:

```yaml
sources:
  - name: profi-backoffice
    kind: backoffice_selenium
    url: "https://profi.ru/backoffice/n.php"
    enabled: true

fetch:
  selenium_headless: false
  selenium_page_wait_seconds: 10
  selenium_profile_path: "/Users/you/Library/Application Support/Google/Chrome"
```

Перед запуском откройте Chrome с этим профилем и войдите в Profi.ru вручную. Если сайт требует
дополнительную проверку, оставьте `selenium_headless: false`, пройдите её в открывшемся окне и
перезапустите мониторинг. Бот не откликается автоматически: он присылает кнопку с URL заказа.

## Конфигурация

Пример `config.yaml`:

```yaml
sources:
  - name: api-orders
    url: "https://profi.ru/rabota/it_freelance/zakazy-na-nastrojku-api/"
    enabled: true
  - name: programmer-orders
    url: "https://profi.ru/rabota/it_freelance/zakazy-dlya-programmistov/"
    enabled: true

filters:
  include_keywords:
    - api
    - интеграция
    - backend
    - telegram
    - bot
    - парсинг
  exclude_keywords:
    - бесплатно
    - студент
    - только с отзывами
  cities:
    - Москва
    - Санкт-Петербург
    - онлайн
  min_price: 3000
  max_price: null

fetch:
  timeout_seconds: 20
  delay_between_requests_seconds: 5
  user_agent: "Mozilla/5.0 profiru-orders-watcher/0.1"

storage:
  sqlite_path: "./data/orders.sqlite3"
```

## Docker

```bash
docker build -t profiru-orders-watcher .
docker run --rm --env-file .env -v $(pwd)/config.yaml:/app/config.yaml profiru-orders-watcher run --config /app/config.yaml
```

## Cron example

```cron
*/5 * * * * cd /opt/profiru-orders-watcher && . .venv/bin/activate && profiru-watch run --config config.yaml >> logs/cron.log 2>&1
```

## Как расширять

1. Добавить новый источник в `config.yaml`.
2. Если структура HTML отличается, добавить или поправить fetcher в `src/profiru_orders_watcher/fetchers/`.
3. Если нужен скоринг под резюме/профиль специалиста, добавить отдельный слой `rankers/` и не смешивать его с парсером.
4. Для автотестов HTML-парсинга положить сохраненный безопасный HTML-фрагмент в `tests/fixtures/`.

## Структура

```text
profiru-orders-watcher/
  src/profiru_orders_watcher/
    cli.py
    config.py
    filters.py
    models.py
    storage.py
    fetchers/
      public_html.py
    notifiers/
      telegram.py
  tests/
  config.example.yaml
  .env.example
  pyproject.toml
  Dockerfile
```

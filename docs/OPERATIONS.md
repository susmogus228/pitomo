# Эксплуатация Petshop API 0.7.1

Поддерживаемое окружение: Python 3.12.14, PostgreSQL 16, Docker Compose v2.
Команды выполняйте из корня проекта. SQLite предназначен для локальных тестов.

## Установка и зависимости

В Windows создайте venv командой `py -3.12 -m venv .venv`, в Linux используйте
`python3.12 -m venv .venv`. Активируйте его средствами своей оболочки.

```text
python -m pip install --require-hashes -r requirements-dev-lock.txt
python -m pip check
python -m ruff check .
python -m unittest discover -s scripts -p "test_*.py"
python -m pytest -q -m "not postgresql"
python -m pip_audit -r requirements-dev-lock.txt --no-deps --disable-pip
```

Production-образ устанавливает `requirements-lock.txt`. Базовые Python/PostgreSQL
образы закреплены digest, GitHub Actions закреплены commit SHA. Оба lock-файла включают
точные версии, транзитивные зависимости и SHA-256 дистрибутивов. Маркеры платформ
позволяют устанавливать их в Windows и Linux. Для обновления зависимостей измените
`requirements.txt` / `requirements-dev.txt`, затем используйте uv 0.12.0:

```text
uv pip compile requirements.txt --python-version 3.12 --universal --generate-hashes --no-annotate --output-file requirements-lock.txt
uv pip compile requirements-dev.txt --python-version 3.12 --universal --generate-hashes --no-annotate --output-file requirements-dev-lock.txt
```

После обновления выполните весь CI. Starlette 1.7.0 исправляет устаревшие импорты
AnyIO, а httpx2 заменяет устаревающий клиент TestClient. Dev-зависимости используют
`requirements-lock.txt` как constraints, поэтому общие версии совпадают с runtime.
CI отдельно проверяет оба lock-файла и запрещает расхождения версий.
Изменения клиента соответствуют
[release notes Starlette](https://starlette.dev/release-notes/) и
[документации TestClient](https://starlette.dev/testclient/).

## Конфигурация

Скопируйте `.env.example` в новый `.env`. Заполните `POSTGRES_PASSWORD`,
`PETSHOP_DATABASE_URL` и отдельный `PETSHOP_JWT_SECRET`. Генератор случайного значения:

```text
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Создайте два разных значения. В Compose URL имеет вид
`postgresql+psycopg://petshop:<password>@postgres:5432/petshop`.
URL-safe пароль можно вставить без преобразования; спецсимволы обычного пароля
нужно URL-кодировать. Файл `.env` содержит секреты: ограничьте его ACL/права и
не включайте его в архив, Git или диагностический вывод `docker compose config`.
Для проверки синтаксиса используйте `docker compose config --quiet`.

| Переменная | Назначение |
|---|---|
| `PETSHOP_ENV` | `development`, `test` или `production`; Compose использует `production` |
| `PETSHOP_DATABASE_URL` | Полный URL базы для API и миграций |
| `PETSHOP_JWT_SECRET` | Обязательный случайный ключ, минимум 32 байта |
| `PETSHOP_ACCESS_TOKEN_MINUTES` | Срок access token; по умолчанию 30 минут |
| `PETSHOP_CORS_ORIGINS` | Origins через запятую, например `https://shop.example.org`; пустое значение отключает CORS |
| `PETSHOP_DOCS_ENABLED` | Доступ к Swagger/OpenAPI; в Compose по умолчанию `false` |
| `PETSHOP_SQL_ECHO` | SQL-диагностика; оставляйте `false` на сервере |
| `PETSHOP_LOGIN_MAX_ATTEMPTS` | По умолчанию 5 попыток на аккаунт; IP-лимит в 10 раз выше |
| `PETSHOP_LOGIN_WINDOW_SECONDS` | Размер окна; по умолчанию 300 секунд |
| `PETSHOP_HTTP_PORT` | Порт API на `127.0.0.1`; по умолчанию 8000 |
| `PETSHOP_POSTGRES_PORT` | Порт БД на `127.0.0.1` при подключённом dev override |
| `PETSHOP_IMAGE` | Тег или digest образа API; по умолчанию `petshop-api:0.13.1` |

Публикуйте API через HTTPS reverse proxy. Контейнер по умолчанию не доверяет
`X-Forwarded-*`; адрес для IP-лимита будет адресом proxy. При настройке доверенных
proxy меняйте параметры Uvicorn только для точных адресов своей сети. Лимит по
учётной записи продолжает действовать. Wildcard origin не поддерживается.

## Первый запуск

```text
docker compose config --quiet
docker compose up --build --detach --wait --wait-timeout 120
python scripts/check_health.py
docker compose ps
```

Compose ожидает готовности PostgreSQL, выполняет `python -m app.db.cli upgrade`
отдельным контейнером и запускает API после успешной миграции. Для пустой базы CLI
создаёт текущую схему и Alembic revision без demo-данных; для существующей применяет
миграции Alembic. API работает под UID 10001,
без `--reload`, с файловой системой read-only и временным `/tmp`.
PostgreSQL не публикует порт на хост. Для локального подключения выберите override:

```text
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --detach postgres
```

Dev override открывает только `127.0.0.1:5432`. У локально запущенного Python
измените hostname в URL на `127.0.0.1`; внутри Compose используйте `postgres`.
Выполните создание администратора через `app.admin.bootstrap` с интерактивным
вводом пароля, как описано в README. Миграция существующей базы не заменяет данные
демонстрационным каталогом. Для демонстрации вызовите `python -m app.db.cli seed`;
команда допускает только пустой каталог. `init --seed` создаёт новую базу с demo.

`docker compose down` останавливает сервисы с сохранением volume. Ключ `--volumes`
удаляет данные и подходит только для одноразового CI.

## Обновление и откат приложения

Перед обновлением сохраните backup и проверьте его восстановление. Соберите новый
образ с отдельным тегом. Миграции выполняйте после проверки, что прежняя версия
API совместима с новой схемой. Для несовместимой миграции запланируйте обслуживание
и отдельную процедуру восстановления данных.

```text
docker build -t petshop-api:0.7.1 .
docker compose run --rm --no-deps migrate
python scripts/release.py --image petshop-api:0.7.1 --timeout 90
```

Перед миграцией задайте `PETSHOP_IMAGE` кандидата в `.env`; сохраните предыдущий
образ локально. `release.py` получает точный image ID работающего API, запускает
кандидата и ожидает Docker healthcheck `/ready`. При неуспехе он запускает API
из прежнего image ID и снова ожидает readiness. Скрипт возвращает код 1 и JSON
`release_failed` даже после успешного отката, чтобы оператор получил сигнал.
Если `rollback_succeeded=false`, требуется вмешательство оператора.

После успешного автоматического отката замените `PETSHOP_IMAGE` в `.env` на значение
`previous_image` из JSON-события **до следующего `docker compose up`**. Если задавали
переменную в оболочке или deployment service, обновите и этот источник. Скрипт
меняет окружение только своего дочернего процесса; сохранённую конфигурацию он
не редактирует. Без этой правки следующий запуск Compose снова выберет кандидата.

Этот способ заменяет один контейнер и допускает короткую недоступность во время
рестарта. Скрипт не откатывает схему или данные. Для первого запуска используйте
Compose; `release.py` требует существующий API-контейнер.

## Backup и проверка восстановления

Установите PostgreSQL 16 client tools или укажите путь к распакованному `bin`
через `--pg-bin`. На Windows PostgreSQL предлагает официальный путь к
[EDB ZIP с бинарниками](https://www.postgresql.org/download/windows/).
Добавьте этот каталог в PATH только текущей оболочки, если нужно.

Задайте `PETSHOP_DATABASE_URL` в окружении процесса. Скрипт не загружает `.env`
самостоятельно, чтобы оператор явно выбирал базу. При Compose БД доступна клиенту
на хосте только с dev override или через защищённое подключение оператора.

```text
python scripts/database_backup.py backup --file backups/petshop-2026-09-29.dump
python scripts/database_backup.py restore --file backups/petshop-2026-09-29.dump
```

Создайте каталог `backups` заранее. Backup использует `pg_dump --format=custom`;
существующий файл он не перезаписывает. Считайте backup успешным только при коде 0:
после ошибки может остаться неполный файл. Сохраняйте архивы вне сервера приложения
с ограничением доступа и шифрованием на стороне хранилища.

Для restore создайте отдельную пустую БД и задайте её URL в
`PETSHOP_RESTORE_DATABASE_URL`. Скрипт запрещает совпадающий адрес исходной базы,
проверяет отсутствие таблиц/последовательностей/views и использует
`pg_restore --single-transaction --exit-on-error --no-owner --no-privileges`.
Для проверки ограничьте роль восстановления доступом только к тестовой БД.
Импортируйте только собственные доверенные дампы.

После восстановления проверьте `alembic current`, число пользователей/заказов и
исторические позиции заказов. Затем запустите API против восстановленной базы
с отдельным ключом и проверьте `/ready`. Backup одной базы не сохраняет роли
PostgreSQL или конфигурацию сервера. Оператор восстанавливает их отдельно.

Пароли передаются дочерним PostgreSQL tools через окружение, без аргументов
процесса. Скрипт скрывает SQL и stderr драйвера. Форматы и гарантии описаны в
[pg_dump](https://www.postgresql.org/docs/16/app-pgdump.html) и
[pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html).

## Наблюдение и PostgreSQL-тесты

`/health` проверяет работу процесса, `/ready` проверяет подключение, таблицы,
столбцы и версию схемы. Docker
проверяет `/ready` каждые 15 секунд. `restart: unless-stopped` перезапускает
завершившийся процесс; статус `unhealthy` сам по себе не вызывает перезапуск.

```text
python scripts/check_health.py --url http://127.0.0.1:8000/ready
docker compose logs --tail 100 api
```

Проверка возвращает JSON event и код 1 при недоступности. Подключите её к своему
мониторингу с интервалом 1 минута и сигналом после трёх ошибок подряд. Настройка
внешнего канала оповещений и расписания относится к окружению эксплуатации;
пакет не отправляет сообщения. Контейнерные логи ограничены тремя файлами по 10 MB.
Для долговременного аудита подключите сбор stdout JSON events приложения.
`/metrics` доступен администратору и содержит счётчики текущего процесса. После
рестарта они сбрасываются; при нескольких процессах агрегируйте их внешним сборщиком.

Для конкурентных интеграционных тестов задайте `PETSHOP_TEST_POSTGRES_URL` только
для отдельной тестовой базы. Тесты создают и удаляют свои изолированные схемы.

```text
python -m pytest -q -m postgresql --strict-markers
```

Без URL PostgreSQL-тесты дают явный skip. GitHub Actions задаёт URL одноразового
PostgreSQL service и запускает этот набор отдельно. CI также проверяет SQLite
в Windows/Linux, Ruff, safety tests, зависимости и полный Compose-startup.
Файл workflow начинает работать после размещения проекта в GitHub; наличие файла
не означает, что CI уже запускался на удалённом runner.

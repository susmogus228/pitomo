# Проверка backend в Docker, 29.09.2026

Проверки завершены на отдельном Compose-проекте `petshop-validation-20260929`. API использовал `127.0.0.1:18080`, PostgreSQL 16.15 использовал `127.0.0.1:25439`. Основной launcher-проект не затрагивался.

## Результат

| Проверка | Подтверждённый результат | Evidence |
| --- | --- | --- |
| Сборка Dockerfile | Образ `petshop-api:container-validation` собран; зависимости установлены из lockfile с проверкой хэшей | Image ID ниже; runtime JSON содержит SHA256 входных файлов |
| Compose и миграции | PostgreSQL и API healthy; migrate завершился с кодом 0; revision `0004_v071`; новый каталог пустой | `smoke-20260929T053953.json` |
| HTTP | 108 реальных HTTP-запросов и 272 assertions прошли, включая ожидаемые ошибки | `real-container-run/*.json` |
| pytest | 201 passed, 0 failures, 0 errors, 0 skipped; 138.983 с; PostgreSQL concurrency cases включены | `all-tests.xml`, `pytest-20260929T054224.json` |
| Operations unit tests | 7 passed, 23 subtests passed | `operations-tests.xml` |
| API restart | Профиль, корзина, заказ, остатки, idempotency и счётчик ограничения входа сохранились | `real-container-run/persistence-20260929T053952.json` |
| Полный Compose stop/start | Данные сохранились после остановки и запуска API и PostgreSQL | `backup-20260929T054307.json` |
| Backup/restore | В отдельной пустой БД совпали хэши строк всех 10 public tables и состояния 5 sequences | `backup-20260929T054307.json` |
| Защита операций | Перезапись dump, restore в непустую и исходную БД отклонены; исходные данные сохранены | `backup-20260929T054307.json` |
| Release rollback | Намеренно unhealthy image отклонён; release.py восстановил прежний immutable image; данные и HTTP-проверки сохранились | `rollback-20260929T054329.json` |
| Runtime | UID/GID `10001:10001`, read-only root, `cap_drop=ALL`, no-new-privileges, loopback binding, healthy, pip check passed | `runtime-20260929T054405.json` |
| Завершение | Только validation stack остановлен; контейнеры и том сохранены | `stop-20260929T054407.json` |

Образ, восстановленный после проверки rollback:

```text
sha256:51176b87479d218867106d3c83d113f4acd80ccc2805fc4442b2e58d5125773f
```

HTTP-проверки охватывают регистрацию и вход, запрет повышения роли клиентом, права каталога, сортировку и фильтры, точные денежные суммы, владение корзиной и заказами, списание остатка один раз, idempotency отдельно для каждого покупателя, неизменность снимка заказа, защиту администратора от самоблокировки и немедленное применение изменения роли/активности.

## Исправления конфигурации проверки

Windows резервирует диапазон `15375–15474`, поэтому порт `15439` отклонился при bind. Для изолированной БД выбран свободный `25439`; системные исключения портов не изменялись.

В подготовленном `runtime.env` URL миграции первоначально указывал БД `petshop`, а `POSTGRES_DB` задавал `petshop_container_test`. URL приведён к фактической БД. Первые два неуспешных запуска сохранены в evidence как история диагностики. Ошибок backend эти запуски не подтвердили.

Код приложения, Dockerfile и исходные Compose-файлы в рамках этой проверки не менялись. Добавлены runner и файлы проверки в `work/container-validation`; исправлены только параметры отдельного validation окружения. Ruff приложения, тестов, operations scripts и новых runners прошёл.

## Сохранённые ресурсы

- PostgreSQL volume: `petshop-validation-20260929_petshop_postgres_data`.
- Исходная БД: `petshop_container_test`.
- БД восстановления: `petshop_restore_test_749c75d8`.
- Dump: `database-7809e526.dump` в этой папке.
- Образы validation baseline и намеренно unhealthy candidate сохранены для воспроизведения.

`private.json`, `runtime.env` и dump остаются в локальной игнорируемой папке `work`. Их нельзя добавлять в выдаваемый ZIP. Evidence содержит синтетические тестовые данные; пароли и токены runners не записывают.

Результат подтверждает локальную работу контейнеров и operations scripts. Он не подтверждает GitHub CI, публичное развёртывание или работу фронтенда.

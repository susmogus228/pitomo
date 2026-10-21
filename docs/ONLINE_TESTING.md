# Проверка Питомо с других устройств

Для реальных пользователей в Казахстане база персональных данных должна
находиться в Казахстане. Приведённая ниже зарубежная VM подходит только для
изолированной проверки с вымышленными данными. Демо-режим не отменяет закон,
если покупатель вводит реальные сведения. До публичной регистрации заполните
и проверьте документы, получателей данных, карту, публикацию отзывов и хранение
резервных копий. [Условия подготовки](PRIVACY_KZ.md).

Сайт, запущенный через `START.bat` на Windows, работает, пока включён этот компьютер.
Для доступа при выключенном домашнем ПК перенесите отдельную **тестовую** копию на
Linux VM. Предпочтительная бесплатная схема: OCI Always Free Ampere A1 + Docker
Compose + Tailscale Funnel. Funnel выдаёт публичный HTTPS-адрес `*.ts.net` без
покупки домена. На VM контейнеры работают независимо от домашнего компьютера.
Развёртывание не выполняется автоматически: нужны ваши аккаунты OCI и Tailscale.

```text
Браузер телефона/ПК → HTTPS Tailscale Funnel на OCI VM
                    → 127.0.0.1:8080 Nginx
                    → внутренняя сеть Compose: API + PostgreSQL
                                            ↘ том с фото отзывов
```

Это тестовый магазин с демонстрационной оплатой; реальные деньги, доставка и
платёжный провайдер не подключены. Публичная ссылка позволяет любому открыть
витрину и зарегистрироваться. Административные операции защищаются проверкой роли
на сервере; сохраняйте пароль администратора вне тестовой переписки.

## Что позволяет бесплатный тариф

По [документации OCI Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
доступный объём Ampere A1 равен 1 500 OCPU-часам и 9 000 GB-часам в месяц,
что для постоянно работающей VM соответствует **2 OCPU и 12 GB RAM**. Ресурсы
создаются в домашнем регионе аккаунта. VM.Standard.E2.1.Micro имеет только 1 GB
RAM; для сборки этого Docker-стека выбирайте A1. OCI может ответить `out of host
capacity`, а малоиспользуемую Always Free VM вправе изъять после семи дней низкой
загрузки. Бесплатный тариф не гарантирует непрерывную доступность. Следите за
меткой **Always Free eligible** и лимитами в консоли; не выбирайте платные
ресурсы и не увеличивайте квоты наугад.

[Tailscale Personal бесплатен для шести пользователей](https://tailscale.com/docs/reference/free-plans-discounts),
а [Funnel доступен на всех планах](https://tailscale.com/docs/features/tailscale-funnel).
Funnel пока beta, имеет ограничения пропускной способности и требует MagicDNS,
HTTPS-сертификаты и разрешение Funnel в tailnet. Его URL публичен; для доступа
только со своих устройств используйте Tailscale Serve вместо Funnel.

## Подготовка VM

1. Создайте в домашнем регионе OCI экземпляр **VM.Standard.A1.Flex**, не более
   доступных Always Free 2 OCPU / 12 GB, с Ubuntu ARM64 и диском в пределах
   бесплатного объёма. Для SSH используйте ключи. Разрешите доступ к SSH только
   с нужных адресов. Порты 8000, 8080 и 5432 наружу не открывайте: Funnel
   соединяется с сервером исходящим соединением.
2. Установите Docker Engine и Compose plugin по
   [официальной инструкции Docker для Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
   Установка меняет систему VM; выполняйте её только после создания своего
   экземпляра. Проверка: `docker version` и `docker compose version`.
3. Установите Tailscale по
   [официальной инструкции для Linux](https://tailscale.com/docs/install/linux),
   выполните `sudo tailscale up` и авторизуйте VM в своём tailnet. В панели
   Tailscale узнайте точное DNS-имя VM вида `pitomo.<tailnet>.ts.net`.
4. Перенесите на VM папку проекта без локальной `.env`, дампов и тестовых БД.
   Не переносите автоматически текущую БД Windows: создайте отдельную тестовую
   базу или восстановите только явно выбранную резервную копию.

Закреплённые базовые образы Python, Node, Nginx и PostgreSQL опубликованы для
`linux/arm64`. **Фактическая сборка всего проекта на OCI A1 ещё не проверена**;
проверка ниже обнаружит несовместимые Python/npm-зависимости, если они появятся.

## Конфигурация тестовой копии

В папке проекта на VM скопируйте `.env.example` в `.env`, ограничьте доступ к
файлу (`chmod 600 .env`) и задайте разные случайные значения для
`POSTGRES_PASSWORD` и `PETSHOP_JWT_SECRET`. В `PETSHOP_DATABASE_URL` укажите
хост `postgres` и тот же пароль БД; не помещайте секреты в README или журнал.
Для публичного теста измените эти поля:

```dotenv
PETSHOP_ENV=development
PETSHOP_DOCS_ENABLED=false
PETSHOP_PUBLIC_HOST=pitomo.example.ts.net
PETSHOP_PUBLIC_ORIGIN=https://pitomo.example.ts.net
PETSHOP_SECURE_COOKIES=true
```

Замените `pitomo.example.ts.net` **одним и тем же фактическим именем** из панели
Tailscale. `PETSHOP_PUBLIC_HOST` не содержит `https://`, порт, путь или `*`.
`PETSHOP_PUBLIC_ORIGIN` содержит ровно `https://` и это имя. Nginx откажется
стартовать при несовпадении; произвольный Host не принимается. Cookie будут
только HTTPS. Для тестовой оплаты нужен режим `development`; это **не** режим
production. `PETSHOP_DOCS_ENABLED=false` оставляет Swagger закрытым. База и
остатки OCI копии не должны зависеть от локального проекта Windows.

После заполнения `.env` выполните в папке проекта:

```sh
sh scripts/linux/oci-readiness.sh
docker compose --project-name pitomo --env-file .env \
  -f docker-compose.yml -f docker-compose.frontend.yml config --quiet
docker compose --project-name pitomo --env-file .env \
  -f docker-compose.yml -f docker-compose.frontend.yml up --build --detach --wait
docker compose --project-name pitomo --env-file .env \
  -f docker-compose.yml -f docker-compose.frontend.yml \
  exec -T api python -m app.db.cli seed-pitomo
curl --fail --silent http://127.0.0.1:8080/ready
docker compose --project-name pitomo --env-file .env \
  -f docker-compose.yml -f docker-compose.frontend.yml ps
```

Compose хранит PostgreSQL и фото отзывов в отдельных named volumes, создаёт
права каталога фото перед стартом API, а `api` и `web` перезапускает при падении
процесса. Все host-порты API и сайта привязаны к `127.0.0.1`; PostgreSQL вообще
не публикует host-порт. Первые сборка и миграция могут занять время. Не
используйте `docker compose down --volumes`: это удалит данные.

Команда `seed-pitomo` добавляет 48 демонстрационных товаров только в отдельную
тестовую базу VM. При повторном запуске она пропускает уже существующие позиции
и не меняет их остатки. Для панели создайте администратора; замените адрес на
свой и введите новый пароль в интерактивном запросе:

```sh
docker compose --project-name pitomo --env-file .env \
  -f docker-compose.yml -f docker-compose.frontend.yml \
  exec api python -m app.admin.bootstrap --email you@example.com --first-name Admin
```

После локальной проверки включите Funnel по
[текущей справке Tailscale CLI](https://tailscale.com/docs/reference/tailscale-cli/funnel):

```sh
sudo tailscale funnel --bg 8080
sudo tailscale funnel status
```

Проверьте полученный HTTPS-адрес на другом устройстве без Tailscale: каталог,
регистрацию тестового покупателя, корзину, заказ, отзывы и фото. Проверьте, что
обычный пользователь не открывает `/admin` и получает отказ на admin API.
`--bg` сохраняет Funnel в фоне и возобновляет его после перезагрузки VM, пока
работает Tailscale; [это описано в CLI](https://tailscale.com/docs/reference/tailscale-cli/funnel).
После перезагрузки проверьте `systemctl is-active docker tailscaled`, `docker
compose ... ps`, `/ready`, `/healthz` и внешний HTTPS-адрес. Обновление `.env` требует
пересоздания затронутых контейнеров через `up --detach --force-recreate`.

## Резервная копия и контроль состояния

Выполняйте периодически `curl --fail http://127.0.0.1:8080/ready` на VM и
проверяйте `docker compose ... ps`; внешний `https://<имя>.ts.net/ready` проверяйте с другого устройства.
Локальный healthcheck и политика перезапуска не заменяют внешнее оповещение.
Пример резервной копии для проекта с именем `pitomo` (выполнять в папке проекта):

```sh
umask 077
mkdir -p backups
stamp="$(date -u +%Y%m%d-%H%M%S)"
docker compose --project-name pitomo --env-file .env \
  -f docker-compose.yml -f docker-compose.frontend.yml \
  exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "backups/pitomo-${stamp}.dump"
docker compose --project-name pitomo --env-file .env \
  -f docker-compose.yml -f docker-compose.frontend.yml \
  exec -T api tar -C /app/uploads/reviews -cf - . \
  > "backups/pitomo-reviews-${stamp}.tar"
```

Проверяйте коды команд и читаемость файлов (`pg_restore --list`, `tar -tf`),
копируйте дамп, архив фото и `.env` в **зашифрованное хранилище вне OCI VM**.
Один дамп БД без фото не восстановит прикреплённые изображения. Эти две команды
не создают единого атомарного снимка; для согласованной копии остановите запись
в магазин на время backup. При переносе восстановите БД и фото в новые volumes,
затем выполните миграции и тест заказа/отзыва **до** включения Funnel.

Если OCI изымет VM или она станет недоступна, создайте новый Always Free экземпляр,
установите Docker/Tailscale, восстановите сохранённые `.env`, БД и фото и снова
проверьте сайт. Новый Tailscale node может получить другое имя: тогда обновите
оба `PETSHOP_PUBLIC_*` значения и публичную ссылку. Это план восстановления,
а не гарантия доступности «в любой момент».

## Быстрый временный просмотр с Windows

Если ПК включён и нужна разовая ссылка, можно использовать
[Cloudflare Quick Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).
Запускайте `cloudflared tunnel --url http://127.0.0.1:<PETSHOP_WEB_PORT>` для
**отдельной тестовой копии**. Он выдаёт случайный `*.trycloudflare.com` адрес;
впишите его hostname в `PETSHOP_PUBLIC_HOST`, полный HTTPS origin в
`PETSHOP_PUBLIC_ORIGIN`, включите `PETSHOP_SECURE_COOKIES=true` и пересоздайте
API/web. При каждом новом адресе повторите настройку. Quick Tunnel существует
только пока работает процесс и включён ПК, поэтому для постоянного доступа не
подходит. Не направляйте его на старый локальный сайт с реальными данными.

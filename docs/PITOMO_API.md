# Pitomo storefront API

For receipt confirmation, reviews, bestseller ranking, discounts and veterinary search added in v0.9.0, see [V0.9.md](V0.9.md).

For the three delivery stages, incidents, versioned admin commands and receipt
restrictions added in v0.13.0, see [V0.13.md](V0.13.md).

The storefront uses the existing `/api/v1` API. Monetary amounts are decimal strings
in KZT; totals, prices and stock are calculated by the server. Product IDs and variant
IDs are different: cart operations take a purchasable `variant_id`.

## Browser authentication

- `POST /auth/register`: `{email,password,first_name,last_name?}` → `201 UserResponse`.
- `POST /auth/browser/login`: `{email,password}` → `200 UserResponse`.
  Requires an explicit same-origin `Origin` header (browsers supply it).
- `GET /auth/session` → `200 UserResponse`, or `401` when expired/absent.
- `POST /auth/logout` → `204`; revokes the server-side browser session and expires cookies.

Login sets `pitomo_session` (HttpOnly, SameSite=Lax, Path=/) and `pitomo_csrf`
(readable by JavaScript, SameSite=Lax, Path=/). Both have the configured access-token
lifetime. They are Secure in production. Session tokens are random and only their
SHA-256 hashes are stored. CSRF values are HMACs bound to individual session tokens.
Send `credentials: 'include'`; every authenticated cookie POST/PUT/PATCH/DELETE must
include `X-CSRF-Token` read from `pitomo_csrf`. The server also checks the exact Origin.
Reverse proxies must preserve Host; production's public scheme must be HTTPS.
`PETSHOP_CORS_ORIGINS` can explicitly allow additional trusted origins. Its default is empty.

Legacy `POST /auth/login` still returns a Bearer JWT. An explicit Bearer authorization
header takes precedence over cookies and does not use CSRF. Browser session tokens
cannot be used as Bearer JWTs. Logout does not revoke separate legacy JWTs.

## Catalog and favorites

`GET /products` accepts `pet_type`: `cat`, `dog`, `bird`, `small_pet`, `fish`, `reptile`,
`amphibian`, `invertebrate`. Existing `category=food|accessory`, `q`, `brand`, price,
stock, sorting and page/page_size filters remain supported.

Product responses include `image_url: string|null` and the existing `description`.
Older products may have no image; the client must render a fallback.

- `GET /favorites` → `ProductResponse[]` for the signed-in user.
- `PUT /favorites/{product_id}` → `204`, idempotent; missing product → `404`.
- `DELETE /favorites/{product_id}` → `204`, idempotent.

## Checkout and orders

`POST /orders` consumes the authenticated user's current cart. Send an
`Idempotency-Key` header (1–128 characters), keep it for retries of the same submission,
and create a new key for a new checkout. Optional body:

```json
{
  "contact_name": "Test Buyer",
  "phone": "+7 700 123 45 67",
  "delivery_method": "pickup",
  "address": null,
  "comment": null,
  "payment_method": "demo"
}
```

`contact_name` and `phone` are required when a body is supplied. Delivery method is
`pickup|delivery`; delivery requires an address of at least 5 characters. Payment method
is `demo|cod`. Unknown fields, including card numbers and client-supplied prices, are rejected.
The old no-body checkout remains supported and defaults to pickup/payment on receipt,
with null contact fields. Shipping is an order instruction only: no shipping cost,
carrier integration or actual delivery scheduling is implemented.

Successful creation → `201 OrderResponse`; a replay returns the same order. Reusing a
key with changed checkout details → `409`. A cancellation does not free an idempotency
key: its replay returns the cancelled order. A new purchase requires a new key/cart.

`GET /orders?limit=20&offset=0` → **array** `OrderResponse[]`, newest first. Default
limit=50, maximum=100. There is no page/page_size or total envelope. Request the next
offset when a full page is returned. `GET /orders/{id}` returns one owned order.

The response keeps all existing snapshot fields and adds:

| Field | Values |
| --- | --- |
| status | `created`, `cancelled` |
| contact_name, phone, address, comment | string or null |
| delivery_method | `pickup`, `delivery` |
| payment_method | `demo`, `cod` |
| payment_status | `pending`, `failed`, `demo_paid`, `cod_pending`, `cancelled` |
| is_demo | true for demonstration payment orders |

`GET /storefront/config` → `{demo_payments_enabled: boolean, currency: "KZT"}`.
`PETSHOP_DEMO_PAYMENTS` defaults to true in development/test and false in production.
Production configuration explicitly enabling demo payments fails validation.

`POST /orders/{id}/demo-payment` with `{outcome:"success"|"failure"}`:

- Demo order: pending/failed → demo_paid on success, or failed on failure.
- Failed payments can be retried; stock remains reserved until cancellation.
- Once demo_paid, repeated success/failure returns the paid order without mutation.
- Cancelled, COD or disabled-demo orders → `409`; another user's order → `404`.
- This endpoint never contacts a provider, charges money, or accepts card information.

`POST /orders/{id}/cancel` cancels an unpaid order and restores stock once. Repeated
cancellation returns the same cancelled order. A demo_paid order returns `409` because
refunds are not implemented. Deleted SKUs stay deleted; cancellation preserves their
historical order snapshots without resurrecting catalog rows. Owner, order and ascending
SKU locks serialize payment/cancellation/checkout operations across workers.

COD orders remain `cod_pending`. Administrators manage delivery stages; customers
confirm receipt at `nearby` without an active incident. Recording collection of
payment is not implemented. Do not display a successful real payment for this state.

## Migration and explicit demonstration assortment

Run the existing database backup workflow before `python -m app.db.cli upgrade`.
Revision `0005_v080` expands the species constraint, adds nullable product image URLs,
backfills legacy order defaults, and adds browser sessions/favorites. Existing products,
users, passwords, inventory and historical order snapshots are preserved. Downgrade is
blocked to avoid dropping storefront data; restore the verified pre-upgrade backup for
an application rollback instead.

`python -m app.db.cli seed-pitomo` adds 48 marked demonstration products across all eight
species. It uses reserved `PITOMO-DEMO-...` SKUs and skips existing keys without changing
their price/stock or any customer product. Repeating it adds zero rows. The original
20-product test/demo seed and its tests remain separate and unchanged.

Image paths use `/media/products/{food,bird-food,hay,toy,bowl,habitat,aquarium,substrate}.png`;
the storefront serves the corresponding illustration assets. The API does not fetch
remote images or silently seed data during startup.

Tests: `tests/test_pitomo.py` covers SQLite/API behavior and migration preservation;
`tests/test_pitomo_postgresql.py` covers concurrent cancellation and payment races with
an explicitly isolated `PETSHOP_TEST_POSTGRES_URL` database whose name contains `test`.

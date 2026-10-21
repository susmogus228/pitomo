# Pitomo storefront

React 19, TypeScript, Vite and React Router. All commerce state comes from the existing
FastAPI backend. The storefront does not contain a hardcoded product catalog.

## Local development

Use Node.js 22.12 or newer. From this directory:

```powershell
npm.cmd ci
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to `http://127.0.0.1:8000` while
preserving Host. The backend must already be running. On Unix use `npm` instead of
`npm.cmd`. The project root Windows launcher provides the packaged Docker workflow.

```powershell
npm.cmd test
npm.cmd run build
```

The build emits `dist/`; the deployment server must serve SPA routes with the
`index.html` fallback and proxy `/api` to the API. Do not serve generated `dist/` on
its own without an API proxy when testing sign-in or checkout.

## Routes

`/` home, `/catalog` URL-backed filters and paging, `/product/:id` variants,
`/favorites`, `/login`, `/register`, `/cart`, `/checkout`, `/orders/:id`,
`/account` profile and `?tab=orders`, `/about`, `/help`.

Guests browse freely. A purchase redirects to sign-in with the selected product,
variant and quantity. After login the pending cart/favorite action is consumed once,
before its API request. It expires after 20 minutes. An uncertain network result
asks the user to inspect their cart/favorites instead of automatically retrying.
Cart, favorites and orders are stored by the API.

## Authentication and checkout

Authentication uses the HttpOnly browser session cookie. No bearer token is stored
in browser storage. Mutations send the readable CSRF cookie as `X-CSRF-Token`.
Login return paths are constrained to internal paths.

Checkout reads `/storefront/config` before allowing submission. Test payment is
disabled if the backend disables it. Demo payment has no card fields and cannot
charge a real payment method. COD records payment-on-receipt intent only.

The checkout retry entry in sessionStorage contains a UUID and SHA-256 fingerprint,
not contact information. The same cart and checkout submission reuse their key.
Successful creation clears the entry. Price and stock calculations stay server-side.

## Assets and motion

Local display font: `/fonts/dela-gothic-one.ttf`, with its license in the same directory.
Illustrations: `/media/hero-cat.png`, `/media/pets-grid.png` and `/media/products/*.png`.
The pet sprite has four columns and two rows in the PETS order from `src/lib.ts`.
Root asset generation owns these files.

The cat and SVG yarn run one 4.8-second CSS sequence; a button replays it. Reduced
motion disables the sequence, hover transforms, and replay button. No animation
library or continuous canvas rendering is needed.

## Verification scope

Unit tests cover API/CSRF behavior, validation errors, safe redirects and checkout
retry keys. They do not substitute for the root workflow's browser tests against
the real backend, visual desktop/mobile checks, or PostgreSQL integration tests.

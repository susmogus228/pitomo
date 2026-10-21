![Pitomo cover](docs/presentation/cover.gif)

[Annotated application walkthrough](docs/presentation/GALLERY.md) · [Static cover](docs/presentation/cover.png)

# Pitomo 0.14.0

Use a local pet-store application to explore a complete shopping and administration workflow: find products, select variants, manage a cart, place a test order and inspect its delivery history. The current application and its screenshots use the **Russian locale**. This English guide explains those screens; it does not imply an English UI.

## Explore the workflows

The React/TypeScript/Vite frontend calls a FastAPI backend with SQLAlchemy, Alembic and PostgreSQL. You can filter the catalog by pet and product category, inspect product photos and discounts, save favorites and use a guest cart. After sign-in, the server merges the guest cart with the account cart.

In checkout, you can choose a saved address or enter one manually. An account holds up to 20 addresses. Reordering starts with a preview using current prices and stock; you confirm before the application adds items to your existing cart. An old order keeps its historical prices.

After receipt, a customer can review purchased products and attach photos. The backend determines the verified-purchase label. Customers can filter reviews and submit reports; administrators can hide or restore reviews with a reason and inspect the moderation audit trail. The admin panel also covers products, stock receipts, orders, delivery stages and filtered CSV/Excel exports.

Start the local application using the repository's Windows instructions and `START.bat` when you intend to install or launch its Docker stack. First setup can require WSL/Docker installation, downloads and a Windows restart. Follow `docs/WINDOWS.md` and preserve an existing store's configuration and database. This guide does not start services or inspect private configuration.

## Screenshot coverage

Use demonstration data and avoid customer contact details or live account information:

1. Catalog: pet/category filters, URL state, search and product cards.
2. Product: variants, gallery, stock, discounts and review distribution.
3. Cart: product images, quantity adjustment and undo removal.
4. Checkout/account: saved addresses and the reorder preview with current prices.
5. Order: three delivery stages, issue state and event history.
6. Admin: a filtered order/stock queue, review moderation and export controls.

Label each screenshot as the current Russian UI. A catalog screenshot alone does not demonstrate checkout, account isolation, moderation or transaction behavior. A screenshot also cannot prove concurrent-stock handling or retry safety; keep those claims tied to their test records.

## Limits

Payment success, refusal and retry use test behavior; the store does not charge money. Real payments, a courier integration, notifications, recommendations, password recovery and permanent hosting are outside the 0.14.0 update. Geoapify address suggestions require its configured service; manual entry remains available. A local store is unavailable when its host computer is off.

Source: current repository README and `docs/V0.14.0.md`, read on 2026-10-21. This guide is a documentation-based overview, not a fresh end-to-end test verdict.

[Original Russian README](README_RU.md)

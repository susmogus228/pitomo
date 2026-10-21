# Pitomo: application walkthrough

Source version 0.14.0; actual local captures on 2026-10-21.

Fresh anonymous captures cover storefront, filters, product, guest cart, mobile, empty cart and sign-in entry. Account-only checkout, address book, reordering, delivery stages, admin stock/moderation and exports are documented in the English guide and source; they were not captured with customer or administrator data in this session. Backend/database records, not these images, support transactions and authorization. Payments are simulated; no live courier integration or hosting is claimed.

## Enter the demonstration storefront

Open the running React/FastAPI shop. The current interface uses Russian; English captions explain the existing application.

![Enter the demonstration storefront](images/home-desktop.jpg)

## Explore the storefront on a narrow screen

Inspect the actual responsive home layout. The cat illustration belongs to the product design, not a screenshot mockup.

![Explore the storefront on a narrow screen](images/home-mobile.jpg)

## Browse demo products

Open the catalog with its category, stock, price and sorting controls. Product records are local demonstration data.

![Browse demo products](images/catalog-desktop.jpg)

## Combine pet and category filters

Filter to cats and toys. The URL and selected chips retain both filters and the response contains one matching item.

![Combine pet and category filters](images/catalog-filters.jpg)

## Inspect a product before adding it

Open the demo cat-food page with its price, stock/variant information and product actions. Prices use tenge in the current locale.

![Inspect a product before adding it](images/product-desktop.jpg)

## Use the anonymous cart

Add one demonstration product. The guest cart shows the item and estimated total; the capture session does not submit an order or payment.

![Use the anonymous cart](images/cart-desktop.jpg)

## Review the cart on a narrow screen

Inspect the same one-item guest cart in the responsive layout. Account merge and stock revalidation need separate behavioral tests.

![Review the cart on a narrow screen](images/cart-mobile.jpg)

## Explain guest retention and the empty state

Remove the capture session item. The empty cart explains 30-day browser retention and the merge after sign-in.

![Explain guest retention and the empty state](images/empty-guest-cart.jpg)

## Inspect the account entry point

Follow the cart sign-in link. The login screen retains the cart return destination. No account credentials or customer data enter these images.

![Inspect the account entry point](images/account-entry.jpg)

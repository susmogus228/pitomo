import { describe, expect, it } from "vitest";
import { routeTitle, productTitle } from "./pageTitles";

describe("descriptive browser titles", () => {
  it("includes the order number for a customer", () => expect(routeTitle("/orders/42")).toBe("Заказ №42 — Питомо"));
  it("distinguishes the admin order context", () => expect(routeTitle("/admin/orders/42")).toBe("Заказ магазина №42 — Питомо"));
  it("uses the actual product name", () => expect(productTitle("Корм для кошек")).toBe("Корм для кошек — Питомо"));
  it("uses a truthful fallback for unknown routes", () => expect(routeTitle("/missing")).toBe("Страница не найдена — Питомо"));
});

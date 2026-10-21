import { describe, expect, it } from "vitest";
import {
  catalogVariant,
  petSwitchParams,
  priceRange,
  updateCatalogParams,
} from "./catalog";
import { availableVariant } from "./lib";
import type { Product, Variant } from "./types";

const variant = (id: number, price: string, stock: number): Variant => ({
  id,
  price,
  stock,
  label: `Option ${id}`,
  sku: `SKU-${id}`,
  currency: "KZT",
});
const product = {
  id: 1,
  name: "Multi-variant product",
  variants: [
    variant(3, "900.00", 0),
    variant(7, "2800.00", 8),
    variant(9, "1900.00", 2),
  ],
} as Product;
describe("catalog variant selection", () => {
  it("matches price and stock on the same SKU, without mutating API data", () => {
    const params = new URLSearchParams(
      "in_stock=true&min_price=1000&max_price=2000",
    );
    expect(catalogVariant(product, params)?.id).toBe(9);
    expect(catalogVariant(product, params)?.price).toBe("1900.00");
    expect(product.variants.map((item) => item.id)).toEqual([3, 7, 9]);
  });
  it("does not borrow the low price of an unavailable SKU", () => {
    expect(
      catalogVariant(
        product,
        new URLSearchParams("in_stock=true&max_price=1000"),
      ),
    ).toBeUndefined();
  });
  it("uses the lowest matching price for the backend price sort when unavailable products are included", () => {
    expect(catalogVariant(product, new URLSearchParams())?.id).toBe(3);
    expect(
      catalogVariant(product, new URLSearchParams("min_price=2000"))?.id,
    ).toBe(7);
  });
  it("selects the cheapest available default variant for home and details", () => {
    expect(availableVariant(product)?.id).toBe(9);
    expect(availableVariant({ ...product, variants: [] })).toBeUndefined();
  });
});
describe("catalog navigation", () => {
  it("preserves food when switching from cats to dogs with food products", () => {
    const source = new URLSearchParams(
      "pet_type=cat&product_kind=food&sort=price_asc&brand=X&page=3",
    );
    const result = petSwitchParams(source, "dog", [
      { id: "food", name: "Корма", count: 2 },
    ]);
    expect(result.params.get("pet_type")).toBe("dog");
    expect(result.params.get("product_kind")).toBe("food");
    expect(result.params.get("sort")).toBe("price_asc");
    expect(result.params.get("brand")).toBe("X");
    expect(result.params.has("page")).toBe(false);
    expect(result.notice).toBe("");
    expect(source.get("pet_type")).toBe("cat");
  });
  it("removes an unsupported kind with an explicit notice and keeps independent filters", () => {
    const result = petSwitchParams(
      new URLSearchParams(
        "pet_type=cat&product_kind=toys&q=blue&min_price=500&in_stock=true",
      ),
      "fish",
      [{ id: "toys", name: "Игрушки", count: 0 }],
    );
    expect(result.params.has("product_kind")).toBe(false);
    expect(result.params.get("q")).toBe("blue");
    expect(result.params.get("min_price")).toBe("500");
    expect(result.params.get("in_stock")).toBe("true");
    expect(result.notice).toContain("«Игрушки»");
    expect(result.notice).toContain("Фильтр раздела снят");
  });
  it("treats a missing kind count as unavailable only during an explicit switch", () => {
    const directUrl = new URLSearchParams("pet_type=fish&product_kind=walking");
    expect(petSwitchParams(directUrl, "amphibian", []).notice).toContain(
      "«Прогулка»",
    );
    expect(directUrl.toString()).toBe("pet_type=fish&product_kind=walking");
  });
  it("keeps a supported kind when returning to all pets and does not invent an unselected filter", () => {
    const result = petSwitchParams(
      new URLSearchParams("pet_type=dog&product_kind=food"),
      "",
      [{ id: "food", name: "Корма", count: 8 }],
    );
    expect(result.params.toString()).toBe("product_kind=food");
    expect(result.notice).toBe("");
    expect(
      petSwitchParams(
        new URLSearchParams("category=food"),
        "dog",
        [],
      ).params.toString(),
    ).toBe("category=food&pet_type=dog");
  });
  it("preserves independent filters and sorting while resetting page", () => {
    const source = new URLSearchParams(
      "q=food&pet_type=cat&sort=price_desc&page=4",
    );
    const result = updateCatalogParams(source, {
      product_kind: "food",
      brand: "Питомо · Демо",
    });
    expect(result.get("page")).toBeNull();
    expect(result.get("q")).toBe("food");
    expect(result.get("sort")).toBe("price_desc");
    expect(result.get("pet_type")).toBe("cat");
    expect(result.get("product_kind")).toBe("food");
    expect(source.get("page")).toBe("4");
  });
  it("removes a chip without discarding other URL state", () => {
    const result = updateCatalogParams(
      new URLSearchParams(
        "pet_type=cat&brand=X&min_price=10&max_price=100&page=2",
      ),
      { min_price: "", max_price: "" },
    );
    expect(result.toString()).toBe("pet_type=cat&brand=X");
  });
});
describe("price ranges", () => {
  it("treats cleared inputs as an unbounded range and preserves zero", () => {
    expect(priceRange("", "")).toEqual({ error: "", min: "", max: "" });
    expect(priceRange("0", "2000")).toEqual({
      error: "",
      min: "0",
      max: "2000",
    });
    expect(priceRange("12.50", "")).toEqual({
      error: "",
      min: "12.5",
      max: "",
    });
  });
  it.each([
    ["3000", "2000"],
    ["-1", ""],
    ["NaN", "20"],
    ["", "Infinity"],
    ["", "10000000000"],
  ])("rejects invalid or reversed input %s to %s", (min, max) => {
    expect(priceRange(min, max).error).toBeTruthy();
  });
});

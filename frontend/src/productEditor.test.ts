import { describe, expect, it } from "vitest";
import { basePrice, blankVariant, editorKinds, normalizedPrice, productCreatePayload, productDraft, productUpdatePayload, variantCreatePayload, variantDraft, variantUpdatePayload } from "./productEditorPayloads";
import type { Product, Variant } from "./types";

const variant: Variant = { id: 12, sku: "CAT-500", label: "500 г", price: "800.00", original_price: "1000.00", discount_percent: 20, stock: 4, currency: "KZT" };
const product: Product = { id: 7, name: "Корм", pet_type: "cat", brand: "Питомо", category: "food", description: "Do not parse this text", composition: "Мясо и рис", material: null, product_kind: "food", variants: [variant] };

describe("admin product payload semantics", () => {
  it("edits the base price under a discount without applying the discount twice", () => {
    expect(basePrice(variant)).toBe("1000.00");
    const draft = variantDraft(variant);
    expect(variantUpdatePayload({ ...draft, label: "Новая упаковка" })).toEqual({ sku: "CAT-500", label: "Новая упаковка", price: "1000.00" });
    expect(basePrice({ price: "0.00", original_price: null })).toBe("0.00");
  });
  it("never patches an existing variant stock through the price editor", () => {
    const payload = variantUpdatePayload({ ...variantDraft(variant), stock: "999" });
    expect(payload).not.toHaveProperty("stock");
    expect(payload).not.toHaveProperty("original_price");
    expect(payload).not.toHaveProperty("discount_percent");
  });
  it("reads composition directly and sends only supported metadata for an immutable category", () => {
    const draft = productDraft(product);
    expect(draft.attribute).toBe("Мясо и рис");
    const payload = productUpdatePayload({ ...draft, name: " Новый корм " });
    expect(payload).toEqual({ name: "Новый корм", pet_type: "cat", brand: "Питомо", product_kind: "food", composition: "Мясо и рис" });
    expect(payload).not.toHaveProperty("category");
    expect(payload).not.toHaveProperty("description");
    expect(payload).not.toHaveProperty("image_url");
    expect(payload).not.toHaveProperty("material");
  });
  it("uses only material for accessories and compatible catalog kinds", () => {
    const draft = productDraft({ ...product, category: "accessory", product_kind: "bowls", composition: null, material: "Керамика" });
    expect(productUpdatePayload(draft)).toHaveProperty("material", "Керамика");
    expect(productUpdatePayload(draft)).not.toHaveProperty("composition");
    expect(editorKinds("food")).toEqual(["food", "treats"]);
    expect(editorKinds("accessory")).not.toContain("food");
    expect(() => productUpdatePayload({ ...draft, product_kind: "food" })).toThrow("категории");
  });
  it("requires at least one unique variant and validates initial stock for creation", () => {
    const draft = productDraft(product);
    const newVariant = { ...blankVariant(), sku: " NEW-1 ", label: "250 г", price: "1200,50", stock: "10" };
    expect(productCreatePayload(draft, [newVariant])).toMatchObject({ category: "food", composition: "Мясо и рис", variants: [{ sku: "NEW-1", label: "250 г", price: "1200.50", stock: 10 }] });
    expect(() => productCreatePayload(draft, [])).toThrow("хотя бы один");
    expect(() => productCreatePayload(draft, [newVariant, { ...newVariant, sku: "new-1" }])).toThrow("уникальными");
    expect(() => variantCreatePayload({ ...newVariant, stock: "1.5" })).toThrow("целым числом");
    expect(() => variantCreatePayload({ ...newVariant, stock: "2147483648" })).toThrow("целым числом");
  });
  it("preserves decimal precision and rejects empty, negative or over-precise prices", () => {
    expect(normalizedPrice("9999999999.99")).toBe("9999999999.99");
    expect(normalizedPrice(" 1,2 ")).toBe("1.20");
    expect(normalizedPrice("0")).toBe("0.00");
    for (const value of ["", "-1", "12.123", "1e3", "10000000000", "NaN"]) expect(() => normalizedPrice(value)).toThrow("Цена");
    expect(() => productUpdatePayload({ ...productDraft(product), attribute: " " })).toThrow("Состав");
  });
});

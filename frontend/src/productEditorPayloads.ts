import { PRODUCT_KINDS } from "./catalog";
import type { PetType, Product, ProductKind, Variant } from "./types";

export interface ProductDraft {
  name: string;
  pet_type: PetType;
  brand: string;
  category: "food" | "accessory";
  product_kind: ProductKind | "";
  attribute: string;
}
export interface VariantDraft { sku: string; label: string; price: string; stock: string }
export function blankVariant(): VariantDraft { return { sku: "", label: "", price: "", stock: "0" }; }
export function editorKinds(category: ProductDraft["category"]): ProductKind[] {
  return (Object.keys(PRODUCT_KINDS) as ProductKind[]).filter((kind) => ["food", "treats"].includes(kind) === (category === "food"));
}
export function productDraft(product?: Product): ProductDraft {
  return product ? { name: product.name, pet_type: product.pet_type, brand: product.brand, category: product.category, product_kind: product.product_kind || "", attribute: (product.category === "food" ? product.composition : product.material) || "" }
    : { name: "", pet_type: "cat", brand: "", category: "food", product_kind: "food", attribute: "" };
}
export function basePrice(variant: Pick<Variant, "price" | "original_price">): string { return variant.original_price ?? variant.price; }
export function variantDraft(variant: Variant): VariantDraft { return { sku: variant.sku, label: variant.label, price: basePrice(variant), stock: String(variant.stock) }; }
function requiredText(value: string, label: string, max: number): string {
  const text = value.trim();
  if (!text || text.length > max) throw new Error(`${label}: укажите от 1 до ${max} символов.`);
  return text;
}
export function normalizedPrice(value: string): string {
  const price = value.trim().replace(",", ".");
  if (!/^\d{1,10}(?:\.\d{1,2})?$/.test(price)) throw new Error("Цена должна быть от 0 до 9 999 999 999,99 ₸, не более двух знаков после запятой.");
  const [whole, fraction = ""] = price.split(".");
  return `${whole.replace(/^0+(?=\d)/, "")}.${fraction.padEnd(2, "0")}`;
}
export function variantUpdatePayload(draft: VariantDraft): { sku: string; label: string; price: string } {
  return { sku: requiredText(draft.sku, "Артикул", 100), label: requiredText(draft.label, "Название варианта", 100), price: normalizedPrice(draft.price) };
}
export function variantCreatePayload(draft: VariantDraft): { sku: string; label: string; price: string; stock: number } {
  if (!/^\d+$/.test(draft.stock.trim()) || Number(draft.stock) > 2147483647) throw new Error("Начальный остаток должен быть целым числом от 0 до 2 147 483 647.");
  return { ...variantUpdatePayload(draft), stock: Number(draft.stock) };
}
export function productUpdatePayload(draft: ProductDraft) {
  if (draft.product_kind && !editorKinds(draft.category).includes(draft.product_kind)) throw new Error("Раздел товара должен соответствовать его категории.");
  return {
    name: requiredText(draft.name, "Название товара", 200),
    pet_type: draft.pet_type,
    brand: requiredText(draft.brand, "Бренд", 100),
    ...(draft.product_kind ? { product_kind: draft.product_kind } : {}),
    ...(draft.category === "food" ? { composition: requiredText(draft.attribute, "Состав", 1000) } : { material: requiredText(draft.attribute, "Материал", 500) }),
  };
}
export function productCreatePayload(draft: ProductDraft, variants: VariantDraft[]) {
  if (!variants.length) throw new Error("Добавьте хотя бы один вариант товара.");
  const items = variants.map(variantCreatePayload);
  if (new Set(items.map((variant) => variant.sku.toLocaleLowerCase())).size !== items.length) throw new Error("Артикулы вариантов должны быть уникальными.");
  return { ...productUpdatePayload(draft), category: draft.category, variants: items };
}

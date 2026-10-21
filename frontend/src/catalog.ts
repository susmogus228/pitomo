import type { Product, ProductKind, ProductKindCount } from "./types";

export const PRODUCT_KINDS: Record<ProductKind, string> = {
  food: "Корма",
  treats: "Лакомства",
  toys: "Игрушки",
  bowls: "Миски и поилки",
  litter: "Наполнители",
  habitats: "Домики и переноски",
  walking: "Прогулка",
  care: "Уход",
  aquatics: "Аквариумистика",
  terrariums: "Террариумы",
};
export function updateCatalogParams(
  current: URLSearchParams,
  changes: Record<string, string>,
) {
  const next = new URLSearchParams(current);
  for (const [key, value] of Object.entries(changes)) {
    if (value) next.set(key, value);
    else next.delete(key);
  }
  next.delete("page");
  return next;
}
export function petSwitchParams(
  current: URLSearchParams,
  pet: string,
  kinds: ProductKindCount[],
) {
  const selectedKind = current.get("product_kind");
  const removedKind =
    selectedKind &&
    !kinds.some((kind) => kind.id === selectedKind && kind.count > 0)
      ? selectedKind
      : null;
  return {
    params: updateCatalogParams(current, {
      pet_type: pet,
      ...(removedKind ? { product_kind: "" } : {}),
    }),
    notice: removedKind
      ? `В разделе «${PRODUCT_KINDS[removedKind as ProductKind] || removedKind}» для выбранного питомца пока нет товаров. Фильтр раздела снят.`
      : "",
  };
}
export function priceRange(min: string, max: string) {
  const minimum = min.trim() === "" ? undefined : Number(min);
  const maximum = max.trim() === "" ? undefined : Number(max);
  if (
    [minimum, maximum].some(
      (value) =>
        value !== undefined &&
        (!Number.isFinite(value) || value < 0 || value > 9999999999.99),
    )
  )
    return { error: "Укажите положительную цену до 9 999 999 999,99 ₸." };
  if (minimum !== undefined && maximum !== undefined && minimum > maximum)
    return { error: "Цена «от» должна быть не выше цены «до»." };
  return {
    error: "",
    min: minimum === undefined ? "" : String(minimum),
    max: maximum === undefined ? "" : String(maximum),
  };
}
export function catalogVariant(product: Product, params: URLSearchParams) {
  const min = params.get("min_price"),
    max = params.get("max_price");
  const matches = product.variants.filter(
    (variant) =>
      (min === null || min === "" || Number(variant.price) >= Number(min)) &&
      (max === null || max === "" || Number(variant.price) <= Number(max)) &&
      (params.get("in_stock") !== "true" || variant.stock > 0),
  );
  return [...matches].sort(
    (a, b) => Number(a.price) - Number(b.price) || a.id - b.id,
  )[0];
}

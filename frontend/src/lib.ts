import type { Cart, PetType, Product } from "./types";

export const PETS: { id: PetType; label: string; forLabel: string }[] = [
  { id: "cat", label: "Кошки", forLabel: "Для кошек" },
  { id: "dog", label: "Собаки", forLabel: "Для собак" },
  { id: "bird", label: "Птицы", forLabel: "Для птиц" },
  {
    id: "small_pet",
    label: "Грызуны и кролики",
    forLabel: "Для грызунов и кроликов",
  },
  { id: "fish", label: "Рыбы", forLabel: "Для рыб" },
  { id: "reptile", label: "Рептилии", forLabel: "Для рептилий" },
  { id: "amphibian", label: "Амфибии", forLabel: "Для амфибий" },
  {
    id: "invertebrate",
    label: "Беспозвоночные",
    forLabel: "Для беспозвоночных",
  },
];
export const money = (value: string | number) =>
  `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(Number(value))} ₸`;
export const itemCount = (count: number) => {
  const tens = count % 100;
  const units = count % 10;
  const noun =
    tens >= 11 && tens <= 14
      ? "товаров"
      : units === 1
        ? "товар"
        : units >= 2 && units <= 4
          ? "товара"
          : "товаров";
  return `${count} ${noun}`;
};
export const dateLabel = (value: string) =>
  new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(value));
export const safeReturnTo = (value: string | null) =>
  value?.startsWith("/") &&
  !value.startsWith("//") &&
  !value.includes("\\") &&
  !/[\u0000-\u001f]/.test(value)
    ? value
    : "/account";
export const productImage = (product: Product) =>
  product.image_url?.startsWith("/media/")
    ? product.image_url
    : `/media/products/${product.category === "food" ? "food" : ["reptile", "amphibian", "invertebrate", "fish"].includes(product.pet_type) ? "habitat" : "bowl"}.png`;
export const availableVariant = (product: Product) =>
  [...product.variants].sort(
    (a, b) =>
      Number(b.stock > 0) - Number(a.stock > 0) ||
      Number(a.price) - Number(b.price) ||
      a.id - b.id,
  )[0];

export function selectFeaturedProducts(products: Product[]): Product[] {
  const species: PetType[] = [
    "cat",
    "bird",
    "reptile",
    "small_pet",
    "dog",
    "fish",
    "amphibian",
    "invertebrate",
  ];
  const usedImages = new Set<string>();
  const selected: Product[] = [];
  for (const petType of species) {
    const product = products.find(
      (item) =>
        item.pet_type === petType &&
        item.image_url?.startsWith("/media/") &&
        !usedImages.has(item.image_url) &&
        item.variants.some((variant) => variant.stock > 0),
    );
    if (product) {
      selected.push(product);
      usedImages.add(product.image_url!);
    }
    if (selected.length === 4) break;
  }
  return selected;
}
export const cartSignature = (cart: Cart) =>
  cart.items
    .map((item) => `${item.variant_id}:${item.quantity}:${item.unit_price}`)
    .sort()
    .join("|");

export async function submissionKey(
  signature: string,
  storage: Storage = sessionStorage,
): Promise<string> {
  const bytes = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(signature),
  );
  const fingerprint = Array.from(new Uint8Array(bytes), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  try {
    const saved = JSON.parse(storage.getItem("pitomo:checkout") || "null") as {
      fingerprint: string;
      key: string;
    } | null;
    if (saved?.fingerprint === fingerprint && typeof saved.key === "string")
      return saved.key;
  } catch {
    /* A malformed previous entry can be replaced safely. */
  }
  const key = crypto.randomUUID();
  storage.setItem("pitomo:checkout", JSON.stringify({ fingerprint, key }));
  return key;
}

export function clearSubmission() {
  sessionStorage.removeItem("pitomo:checkout");
}

export type PendingIntent =
  | {
      action: "add_cart";
      productId: number;
      variantId: number;
      quantity: number;
      createdAt: number;
    }
  | { action: "favorite"; productId: number; createdAt: number };

export const PENDING_INTENT_KEY = "pitomo:pending-intent";
export const PENDING_INTENT_TTL = 20 * 60 * 1000;

function parsePendingIntent(
  raw: string | null,
  now: number,
): PendingIntent | null {
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object") return null;
    const intent = value as Record<string, unknown>;
    const validId = (id: unknown) =>
      typeof id === "number" &&
      Number.isSafeInteger(id) &&
      id > 0 &&
      id <= 2147483647;
    if (
      !validId(intent.productId) ||
      typeof intent.createdAt !== "number" ||
      !Number.isFinite(intent.createdAt) ||
      now - intent.createdAt > PENDING_INTENT_TTL ||
      intent.createdAt - now > 60000
    )
      return null;
    if (intent.action === "favorite")
      return {
        action: "favorite",
        productId: intent.productId as number,
        createdAt: intent.createdAt,
      };
    if (
      intent.action === "add_cart" &&
      validId(intent.variantId) &&
      typeof intent.quantity === "number" &&
      Number.isSafeInteger(intent.quantity) &&
      intent.quantity > 0 &&
      intent.quantity <= 10000
    ) {
      return {
        action: "add_cart",
        productId: intent.productId as number,
        variantId: intent.variantId as number,
        quantity: intent.quantity,
        createdAt: intent.createdAt,
      };
    }
  } catch {
    /* Invalid saved actions must never reach the API. */
  }
  return null;
}

export function savePendingIntent(
  intent:
    | Omit<Extract<PendingIntent, { action: "add_cart" }>, "createdAt">
    | Omit<Extract<PendingIntent, { action: "favorite" }>, "createdAt">,
  storage: Storage = sessionStorage,
  now = Date.now(),
): void {
  const value = { ...intent, createdAt: now };
  if (!parsePendingIntent(JSON.stringify(value), now))
    throw new Error(
      "Не удалось сохранить выбранный товар. Попробуйте ещё раз.",
    );
  storage.setItem(PENDING_INTENT_KEY, JSON.stringify(value));
}

export function readPendingIntent(
  storage: Storage = sessionStorage,
  now = Date.now(),
): PendingIntent | null {
  try {
    return parsePendingIntent(storage.getItem(PENDING_INTENT_KEY), now);
  } catch {
    return null;
  }
}

export async function replayPendingIntent(
  execute: (intent: PendingIntent) => Promise<void>,
  storage: Storage = sessionStorage,
  now = Date.now(),
): Promise<PendingIntent | null> {
  const raw = storage.getItem(PENDING_INTENT_KEY);
  storage.removeItem(PENDING_INTENT_KEY);
  const intent = parsePendingIntent(raw, now);
  if (!intent) return null;
  await execute(intent);
  return intent;
}

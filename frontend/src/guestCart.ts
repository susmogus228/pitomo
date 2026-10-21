import type { Cart } from "./types";

export const GUEST_CART_KEY = "pitomo.guest-cart.v1";
export const GUEST_CART_TTL = 30 * 24 * 60 * 60 * 1000;
export const GUEST_CART_LIMIT = 50;
export interface GuestRow {
  variant_id: number;
  quantity: number;
  product_id: number;
  product_name: string;
  label: string;
  sku: string;
  unit_price: string;
  image_url: string | null;
  available_stock: number;
}
export interface GuestPending {
  owner_id: number;
  operation_key: string;
  items: { variant_id: number; quantity: number }[];
}
export interface GuestState {
  rows: GuestRow[];
  pending: GuestPending | null;
  paused_owner_id?: number;
}
interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}
const empty = (): GuestState => ({ rows: [], pending: null });
const positive = (value: unknown, max = 2147483647): value is number =>
  Number.isSafeInteger(value) && Number(value) > 0 && Number(value) <= max;
const text = (value: unknown, max: number): value is string =>
  typeof value === "string" && value.length <= max;

function parse(raw: string | null, now: number): GuestState | null {
  try {
    if (!raw || raw.length > 100000) return null;
    const data = JSON.parse(raw);
    if (
      data.version !== 1 ||
      !Number.isFinite(data.expires_at) ||
      data.expires_at <= now ||
      data.expires_at > now + GUEST_CART_TTL ||
      !Array.isArray(data.rows) ||
      data.rows.length > GUEST_CART_LIMIT
    )
      return null;
    const used = new Set<number>();
    const rows: GuestRow[] = [];
    for (const row of data.rows) {
      if (
        !positive(row.variant_id) ||
        used.has(row.variant_id) ||
        !positive(row.quantity, 10000) ||
        !positive(row.product_id) ||
        !text(row.product_name, 300) ||
        !text(row.label, 200) ||
        !text(row.sku, 100) ||
        typeof row.unit_price !== "string" ||
        !/^\d{1,12}(\.\d{1,2})?$/.test(row.unit_price) ||
        !Number.isSafeInteger(row.available_stock) ||
        row.available_stock < 0 ||
        row.available_stock > 2147483647 ||
        !(
          row.image_url === null ||
          (text(row.image_url, 500) &&
            row.image_url.startsWith("/media/") &&
            !row.image_url.includes("\\"))
        )
      )
        return null;
      used.add(row.variant_id);
      rows.push({
        variant_id: row.variant_id,
        quantity: row.quantity,
        product_id: row.product_id,
        product_name: row.product_name,
        label: row.label,
        sku: row.sku,
        unit_price: row.unit_price,
        image_url: row.image_url,
        available_stock: row.available_stock,
      });
    }
    let pending: GuestPending | null = null;
    if (data.pending) {
      const value = data.pending;
      if (
        !positive(value.owner_id) ||
        typeof value.operation_key !== "string" ||
        !/^[A-Za-z0-9_-]{8,128}$/.test(value.operation_key) ||
        !Array.isArray(value.items) ||
        !value.items.length ||
        value.items.length > GUEST_CART_LIMIT
      )
        return null;
      const ids = new Set<number>();
      const items: GuestPending["items"] = [];
      for (const item of value.items) {
        if (
          !positive(item.variant_id) ||
          !positive(item.quantity, 10000) ||
          ids.has(item.variant_id)
        )
          return null;
        ids.add(item.variant_id);
        items.push({ variant_id: item.variant_id, quantity: item.quantity });
      }
      pending = {
        owner_id: value.owner_id,
        operation_key: value.operation_key,
        items,
      };
    }
    if (data.paused_owner_id !== undefined && !positive(data.paused_owner_id))
      return null;
    return {
      rows,
      pending,
      ...(data.paused_owner_id
        ? { paused_owner_id: data.paused_owner_id }
        : {}),
    };
  } catch {
    return null;
  }
}

export function createGuestCartStorage(
  provider: () => StorageLike | undefined,
) {
  let memory: string | null = null;
  let memoryOnly = false;
  const read = (now = Date.now()): GuestState => {
    if (!memoryOnly) {
      try {
        const storage = provider();
        if (storage) memory = storage.getItem(GUEST_CART_KEY);
        else memoryOnly = true;
      } catch {
        memoryOnly = true;
      }
    }
    return parse(memory, now) || empty();
  };
  const save = (state: GuestState, now = Date.now()): boolean => {
    const raw = JSON.stringify({
      version: 1,
      expires_at: now + GUEST_CART_TTL,
      ...state,
    });
    const clean = parse(raw, now);
    if (!clean)
      throw Error(
        "Не удалось сохранить корзину. Проверьте количество товаров.",
      );
    memory = JSON.stringify({
      version: 1,
      expires_at: now + GUEST_CART_TTL,
      ...clean,
    });
    try {
      const storage = provider();
      if (!storage) {
        memoryOnly = true;
        return false;
      }
      storage.setItem(GUEST_CART_KEY, memory);
      memoryOnly = false;
      return true;
    } catch {
      memoryOnly = true;
      return false;
    }
  };
  const clear = (now = Date.now()) => save(empty(), now);
  return { read, save, clear, memoryOnly: () => memoryOnly };
}
export const guestCartStorage = createGuestCartStorage(() => {
  try {
    return typeof window === "undefined" ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
});
export function mergeGuestResults(
  rows: GuestRow[],
  results: { variant_id: number; added_quantity: number }[],
): GuestRow[] {
  const confirmed = new Map(
    results.map((item) => [item.variant_id, item.added_quantity]),
  );
  return rows
    .map((row) => ({
      ...row,
      quantity: Math.max(
        0,
        row.quantity - (confirmed.get(row.variant_id) || 0),
      ),
    }))
    .filter((row) => row.quantity > 0);
}
export function guestCartView(rows: GuestRow[]): Cart {
  const items = rows.map((row) => ({
    ...row,
    currency: "KZT",
    is_available: row.quantity <= row.available_stock,
    line_total: (Number(row.unit_price) * row.quantity).toFixed(2),
  }));
  return {
    user_id: 0,
    items,
    total_items: rows.reduce((sum, row) => sum + row.quantity, 0),
    subtotal: items
      .reduce((sum, row) => sum + Number(row.line_total), 0)
      .toFixed(2),
    currency: "KZT",
    can_checkout: false,
  };
}

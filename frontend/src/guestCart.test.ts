import { describe, expect, it } from "vitest";
import {
  createGuestCartStorage,
  GUEST_CART_KEY,
  GUEST_CART_TTL,
  guestCartView,
  mergeGuestResults,
} from "./guestCart";

const row = {
  variant_id: 4,
  quantity: 3,
  product_id: 2,
  product_name: "Корм",
  label: "500 г",
  sku: "SKU",
  unit_price: "2300.00",
  image_url: "/media/food.png",
  available_stock: 9,
};
const storage = () => {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
};
describe("guest cart boundaries", () => {
  it("expires without retaining contact or address fields", () => {
    const memory = storage();
    const guest = createGuestCartStorage(() => memory);
    const withPrivateField = { ...row, phone: "private" };
    guest.save({ rows: [withPrivateField], pending: null }, 10);
    expect(JSON.stringify(guest.read(11))).not.toContain("private");
    expect(guest.read(11).rows).toEqual([row]);
    expect(guest.read(GUEST_CART_TTL + 11).rows).toEqual([]);
  });
  it("keeps the newest state in memory when browser writes fail", () => {
    const guest = createGuestCartStorage(() => ({
      getItem: () => null,
      setItem: () => {
        throw Error("denied");
      },
      removeItem: () => {
        throw Error("denied");
      },
    }));
    expect(guest.save({ rows: [row], pending: null }, 10)).toBe(false);
    expect(guest.read(11).rows).toEqual([row]);
    guest.clear(12);
    expect(guest.read(13).rows).toEqual([]);
  });
  it("binds pending merge to its account and preserves the operation key", () => {
    const memory = storage();
    const guest = createGuestCartStorage(() => memory);
    const pending = {
      owner_id: 7,
      operation_key: "unique-key-123",
      items: [{ variant_id: 4, quantity: 3 }],
    };
    guest.save({ rows: [row], pending }, 10);
    expect(guest.read(11).pending).toEqual(pending);
  });
  it("retains the account pause marker after a confirmed partial merge", () => {
    const memory = storage();
    const guest = createGuestCartStorage(() => memory);
    guest.save({ rows: [row], pending: null, paused_owner_id: 7 }, 10);
    expect(guest.read(11).paused_owner_id).toBe(7);
  });
  it("subtracts only confirmed quantities and preserves rows added during a request", () => {
    expect(
      mergeGuestResults(
        [{ ...row, quantity: 5 }],
        [{ variant_id: 4, added_quantity: 2 }],
      )[0].quantity,
    ).toBe(3);
    expect(
      mergeGuestResults([row], [{ variant_id: 4, added_quantity: 3 }]),
    ).toEqual([]);
    expect(
      mergeGuestResults([row], [{ variant_id: 4, added_quantity: 0 }]),
    ).toEqual([row]);
  });
  it("uses display estimates without permitting guest checkout", () => {
    const cart = guestCartView([row]);
    expect(cart.user_id).toBe(0);
    expect(cart.subtotal).toBe("6900.00");
    expect(cart.can_checkout).toBe(false);
  });
  it("rejects malformed ids, duplicate rows and untrusted image origins", () => {
    const memory = storage();
    const guest = createGuestCartStorage(() => memory);
    for (const rows of [
      [{ ...row, quantity: -1 }],
      [{ ...row, variant_id: "4" }],
      [row, row],
      [{ ...row, image_url: "https://tracker.invalid/secret" }],
    ]) {
      memory.setItem(
        GUEST_CART_KEY,
        JSON.stringify({
          version: 1,
          expires_at: GUEST_CART_TTL,
          rows,
          pending: null,
        }),
      );
      expect(guest.read(1).rows).toEqual([]);
    }
  });
  it("reads changes from another tab and does not resurrect stale persistent state after a failed write", () => {
    const memory = storage();
    const guest = createGuestCartStorage(() => memory);
    guest.save({ rows: [row], pending: null }, 10);
    memory.setItem(
      GUEST_CART_KEY,
      JSON.stringify({
        version: 1,
        expires_at: GUEST_CART_TTL,
        rows: [{ ...row, quantity: 1 }],
        pending: null,
      }),
    );
    expect(guest.read(11).rows[0].quantity).toBe(1);
    const original = memory.setItem;
    memory.setItem = () => {
      throw Error("quota");
    };
    expect(
      guest.save({ rows: [{ ...row, quantity: 5 }], pending: null }, 12),
    ).toBe(false);
    expect(guest.read(13).rows[0].quantity).toBe(5);
    memory.setItem = original;
    guest.save({ rows: [{ ...row, quantity: 6 }], pending: null }, 14);
    expect(guest.read(15).rows[0].quantity).toBe(6);
  });
  it("rejects an expired or oversized pending envelope", () => {
    const memory = storage();
    const guest = createGuestCartStorage(() => memory);
    memory.setItem(
      GUEST_CART_KEY,
      JSON.stringify({
        version: 1,
        expires_at: GUEST_CART_TTL + 100,
        rows: [row],
        pending: null,
      }),
    );
    expect(guest.read(1).rows).toEqual([]);
    expect(() =>
      guest.save(
        {
          rows: Array.from({ length: 51 }, (_, index) => ({
            ...row,
            variant_id: index + 1,
          })),
          pending: null,
        },
        10,
      ),
    ).toThrow();
  });
});

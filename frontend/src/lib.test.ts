import { describe, expect, it, vi } from "vitest";
import {
  cartSignature,
  safeReturnTo,
  submissionKey,
  selectFeaturedProducts,
  savePendingIntent,
  readPendingIntent,
  replayPendingIntent,
  PENDING_INTENT_KEY,
  PENDING_INTENT_TTL,
} from "./lib";
import type { Cart, Product, PetType } from "./types";

class MemoryStorage implements Storage {
  values = new Map<string, string>();
  get length() {
    return this.values.size;
  }
  clear() {
    this.values.clear();
  }
  getItem(key: string) {
    return this.values.get(key) || null;
  }
  key(index: number) {
    return [...this.values.keys()][index] || null;
  }
  removeItem(key: string) {
    this.values.delete(key);
  }
  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

describe("guest actions after sign-in", () => {
  const now = 1800000000000;
  it("preserves the requested variant and quantity and removes intent before a single replay", async () => {
    const storage = new MemoryStorage();
    savePendingIntent(
      { action: "add_cart", productId: 13, variantId: 29, quantity: 3 },
      storage,
      now,
    );
    expect(readPendingIntent(storage, now)).toEqual({
      action: "add_cart",
      productId: 13,
      variantId: 29,
      quantity: 3,
      createdAt: now,
    });
    const execute = vi.fn(async () => {
      expect(storage.getItem(PENDING_INTENT_KEY)).toBeNull();
    });
    await Promise.all([
      replayPendingIntent(execute, storage, now),
      replayPendingIntent(execute, storage, now),
    ]);
    expect(execute).toHaveBeenCalledTimes(1);
    expect(execute).toHaveBeenCalledWith({
      action: "add_cart",
      productId: 13,
      variantId: 29,
      quantity: 3,
      createdAt: now,
    });
  });
  it("replays a guest favorite as an add intent using only a product id", async () => {
    const storage = new MemoryStorage();
    savePendingIntent({ action: "favorite", productId: 17 }, storage, now);
    expect(
      Object.keys(JSON.parse(storage.getItem(PENDING_INTENT_KEY)!)).sort(),
    ).toEqual(["action", "createdAt", "productId"]);
    const execute = vi.fn(async () => {});
    expect(await replayPendingIntent(execute, storage, now)).toEqual({
      action: "favorite",
      productId: 17,
      createdAt: now,
    });
    expect(await replayPendingIntent(execute, storage, now)).toBeNull();
    expect(execute).toHaveBeenCalledTimes(1);
  });
  it("does not replay an expired or future-dated action", async () => {
    const storage = new MemoryStorage();
    const execute = vi.fn(async () => {});
    savePendingIntent({ action: "favorite", productId: 17 }, storage, now);
    expect(readPendingIntent(storage, now + PENDING_INTENT_TTL + 1)).toBeNull();
    expect(
      await replayPendingIntent(execute, storage, now + PENDING_INTENT_TTL + 1),
    ).toBeNull();
    savePendingIntent(
      { action: "favorite", productId: 17 },
      storage,
      now + 120000,
    );
    expect(await replayPendingIntent(execute, storage, now)).toBeNull();
    expect(execute).not.toHaveBeenCalled();
    expect(storage.getItem(PENDING_INTENT_KEY)).toBeNull();
  });
  it("does not retry a failed or ambiguous mutation automatically", async () => {
    const storage = new MemoryStorage();
    savePendingIntent(
      { action: "add_cart", productId: 13, variantId: 29, quantity: 3 },
      storage,
      now,
    );
    const execute = vi.fn(async () => {
      throw new Error("Connection lost after request");
    });
    await expect(replayPendingIntent(execute, storage, now)).rejects.toThrow(
      "Connection lost after request",
    );
    expect(await replayPendingIntent(execute, storage, now)).toBeNull();
    expect(execute).toHaveBeenCalledTimes(1);
  });
  it("rejects malformed ids, quantities and unknown actions before the API", async () => {
    const storage = new MemoryStorage();
    const execute = vi.fn(async () => {});
    for (const input of [
      { action: "add_cart", productId: 1, variantId: 2, quantity: -1 },
      { action: "favorite", productId: "../users" },
      { action: "delete", productId: 3 },
    ]) {
      storage.setItem(
        PENDING_INTENT_KEY,
        JSON.stringify({ ...input, createdAt: now }),
      );
      expect(await replayPendingIntent(execute, storage, now)).toBeNull();
    }
    expect(execute).not.toHaveBeenCalled();
  });
});

describe("curated home assortment", () => {
  const product = (
    id: number,
    pet_type: PetType,
    image_url: string | null,
    stock = 5,
  ) => ({ id, pet_type, image_url, variants: [{ stock }] }) as Product;
  it("selects four available products with different animals and different images", () => {
    const selected = selectFeaturedProducts([
      product(1, "cat", "/media/products/food.png"),
      product(2, "cat", "/media/products/bowl.png"),
      product(3, "bird", "/media/products/bird-food.png"),
      product(4, "reptile", "/media/products/food.png"),
      product(5, "reptile", "/media/products/habitat.png"),
      product(6, "small_pet", "/media/products/hay.png"),
      product(7, "dog", "/media/products/toy.png"),
    ]);
    expect(selected.map((item) => item.id)).toEqual([1, 3, 5, 6]);
    expect(new Set(selected.map((item) => item.pet_type)).size).toBe(4);
    expect(new Set(selected.map((item) => item.image_url)).size).toBe(4);
  });
  it("skips unavailable or missing illustrations without inventing products", () => {
    expect(
      selectFeaturedProducts([
        product(1, "cat", null),
        product(2, "bird", "/media/food.png", 0),
      ]),
    ).toEqual([]);
    expect(selectFeaturedProducts([])).toEqual([]);
  });
});

describe("checkout retries", () => {
  it("keeps one idempotency key across retries and creates a new one for changed input", async () => {
    const storage = new MemoryStorage();
    const first = await submissionKey("cart-1|contact-A|demo", storage);
    expect(await submissionKey("cart-1|contact-A|demo", storage)).toBe(first);
    expect(await submissionKey("cart-1|contact-B|demo", storage)).not.toBe(
      first,
    );
    expect(await submissionKey("cart-2|contact-B|demo", storage)).not.toBe(
      first,
    );
  });
  it("stores no address or contact details in the checkout retry record", async () => {
    const storage = new MemoryStorage();
    await submissionKey("Alice|+7 1234567890|Private address 17|cart", storage);
    expect(storage.getItem("pitomo:checkout")).not.toContain("Alice");
    expect(storage.getItem("pitomo:checkout")).not.toContain("Private");
    expect(
      Object.keys(JSON.parse(storage.getItem("pitomo:checkout")!)),
    ).toEqual(["fingerprint", "key"]);
  });
  it("recovers from a malformed stored record", async () => {
    const storage = new MemoryStorage();
    storage.setItem("pitomo:checkout", "{bad-json");
    expect(await submissionKey("cart", storage)).toMatch(/^[0-9a-f-]{36}$/);
  });
  it("uses variant, quantity and price in a stable cart fingerprint", () => {
    const first = {
      items: [
        { variant_id: 10, quantity: 2, unit_price: "400.00" },
        { variant_id: 3, quantity: 1, unit_price: "50.00" },
      ],
    } as Cart;
    expect(cartSignature(first)).toBe(
      cartSignature({ ...first, items: [...first.items].reverse() }),
    );
    expect(cartSignature(first)).not.toBe(
      cartSignature({ ...first, items: [{ ...first.items[0], quantity: 3 }] }),
    );
  });
});

describe("login redirects", () => {
  it("preserves an internal product variant and quantity", () => {
    expect(safeReturnTo("/product/12?variant=17&qty=2")).toBe(
      "/product/12?variant=17&qty=2",
    );
  });
  it.each([
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "javascript:alert(1)",
    "/\n/evil.example",
    null,
  ])("rejects an external or malformed return path: %s", (path) => {
    expect(safeReturnTo(path)).toBe("/account");
  });
});

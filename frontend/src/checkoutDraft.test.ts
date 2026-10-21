import { describe, expect, it } from "vitest";
import {
  CHECKOUT_DRAFT_TTL,
  clearCheckoutDraft,
  readCheckoutDraft,
  saveCheckoutDraft,
  type CheckoutDraft,
} from "./checkoutDraft";

function storage() {
  const values = new Map<string, string>();
  return {
    values,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
}
const draft: CheckoutDraft = {
  contactName: "Иван Тестовый",
  phone: "+7 700 123 45 67",
  comment: "Позвонить",
  delivery: "delivery",
  payment: "cod",
  address: "Алматы, Абая, 10",
  point: { lat: 43.2, lon: 76.9 },
  details: { apartment: "42", entrance: "2", floor: "3" },
};

describe("private checkout drafts", () => {
  it("restores all checkout fields for the same user within the TTL", () => {
    const store = storage();
    expect(saveCheckoutDraft(7, draft, store, 1000)).toBe(true);
    expect(readCheckoutDraft(7, store, 1001)).toEqual(draft);
  });
  it("never restores another user's contact or address details", () => {
    const store = storage();
    saveCheckoutDraft(7, draft, store, 1000);
    expect(readCheckoutDraft(8, store, 1001)).toBeNull();
    expect(store.values.size).toBe(0);
  });
  it("removes expired drafts rather than refreshing their lifetime on read", () => {
    const store = storage();
    saveCheckoutDraft(7, draft, store, 1000);
    expect(readCheckoutDraft(7, store, 1000 + CHECKOUT_DRAFT_TTL)).toBeNull();
    expect(store.values.size).toBe(0);
  });
  it("ignores malformed and out-of-range stored payloads", () => {
    const store = storage();
    saveCheckoutDraft(7, draft, store, 1000);
    const [key, raw] = [...store.values][0];
    const data = JSON.parse(raw);
    data.draft.point.lat = 100;
    store.setItem(key, JSON.stringify(data));
    expect(readCheckoutDraft(7, store, 1001)).toBeNull();
    store.setItem(key, "{invalid");
    expect(readCheckoutDraft(7, store, 1001)).toBeNull();
  });
  it("does not store unauthenticated data and clears after completion or logout", () => {
    const store = storage();
    expect(saveCheckoutDraft(undefined, draft, store, 1000)).toBe(false);
    saveCheckoutDraft(7, draft, store, 1000);
    clearCheckoutDraft(store);
    expect(readCheckoutDraft(7, store, 1001)).toBeNull();
  });
  it("continues safely when private browsing or quota prevents storage", () => {
    const blocked = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("quota");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    };
    expect(saveCheckoutDraft(7, draft, blocked)).toBe(false);
    expect(readCheckoutDraft(7, blocked)).toBeNull();
    expect(() => clearCheckoutDraft(blocked)).not.toThrow();
  });
});

import type { AddressDetails } from "./address";
import type { GeoPoint } from "./geo";
import { validPoint } from "./geo";
export const CHECKOUT_DRAFT_TTL = 2 * 60 * 60 * 1000;
export interface CheckoutDraft {
  contactName: string;
  phone: string;
  comment: string;
  delivery: "pickup" | "delivery";
  payment: "demo" | "cod";
  address: string;
  point: GeoPoint | null;
  details: AddressDetails;
}
export interface DraftStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}
const KEY = "pitomo.checkout-draft.v1";
function sessionStore(): DraftStorage | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.sessionStorage;
  } catch {
    return undefined;
  }
}
function isDraft(value: unknown): value is CheckoutDraft {
  if (!value || typeof value !== "object") return false;
  const data = value as CheckoutDraft;
  const bounded = (text: unknown, max: number) =>
    typeof text === "string" && text.length <= max;
  return (
    bounded(data.contactName, 100) &&
    bounded(data.phone, 32) &&
    bounded(data.comment, 1000) &&
    bounded(data.address, 350) &&
    (data.delivery === "pickup" || data.delivery === "delivery") &&
    (data.payment === "demo" || data.payment === "cod") &&
    (data.point === null ||
      (typeof data.point === "object" && validPoint(data.point))) &&
    Boolean(data.details) &&
    bounded(data.details.apartment, 30) &&
    bounded(data.details.entrance, 30) &&
    bounded(data.details.floor, 20)
  );
}
export function readCheckoutDraft(
  userId?: number,
  storage = sessionStore(),
  now = Date.now(),
): CheckoutDraft | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (
      !Number.isSafeInteger(userId) ||
      data.version !== 1 ||
      data.userId !== userId ||
      !Number.isFinite(data.expiresAt) ||
      data.expiresAt <= now ||
      data.expiresAt > now + CHECKOUT_DRAFT_TTL ||
      !isDraft(data.draft)
    ) {
      storage.removeItem(KEY);
      return null;
    }
    return data.draft;
  } catch {
    clearCheckoutDraft(storage);
    return null;
  }
}
export function saveCheckoutDraft(
  userId: number | undefined,
  draft: CheckoutDraft,
  storage = sessionStore(),
  now = Date.now(),
): boolean {
  if (!storage || !Number.isSafeInteger(userId) || !isDraft(draft))
    return false;
  try {
    storage.setItem(
      KEY,
      JSON.stringify({
        version: 1,
        userId,
        expiresAt: now + CHECKOUT_DRAFT_TTL,
        draft,
      }),
    );
    return true;
  } catch {
    return false;
  }
}
export function clearCheckoutDraft(storage = sessionStore()): void {
  try {
    storage?.removeItem(KEY);
  } catch {
    /* Checkout remains usable when browser storage is unavailable. */
  }
}

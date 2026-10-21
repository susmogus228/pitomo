export interface PendingRepeat {
  owner_id: number;
  order_id: number;
  fingerprint: string;
  operation_key: string;
}
interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}
export const REPEAT_OPERATION_TTL = 2 * 60 * 60 * 1000;
const memory = new Map<string, string | null>();
const memoryOnly = new Set<string>();
const keyFor = (owner: number, order: number) =>
  `pitomo.repeat.${owner}.${order}`;
const storage = () => {
  try {
    return typeof window === "undefined" ? undefined : window.sessionStorage;
  } catch {
    return undefined;
  }
};
export function readRepeatOperation(
  owner: number,
  order: number,
  store: StorageLike | undefined = storage(),
  now = Date.now(),
): PendingRepeat | null {
  const key = keyFor(owner, order);
  let raw = memory.get(key) || null;
  try {
    if (store && !memoryOnly.has(key)) raw = store.getItem(key);
  } catch {
    memoryOnly.add(key);
  }
  try {
    const data = JSON.parse(raw || "null");
    if (
      !data ||
      data.owner_id !== owner ||
      data.order_id !== order ||
      data.expires_at <= now ||
      data.expires_at > now + REPEAT_OPERATION_TTL ||
      typeof data.fingerprint !== "string" ||
      !/^[a-f0-9]{64}$/.test(data.fingerprint) ||
      typeof data.operation_key !== "string" ||
      !/^[A-Za-z0-9_-]{8,128}$/.test(data.operation_key)
    )
      return null;
    return {
      owner_id: owner,
      order_id: order,
      fingerprint: data.fingerprint,
      operation_key: data.operation_key,
    };
  } catch {
    return null;
  }
}
export function saveRepeatOperation(
  value: PendingRepeat,
  store: StorageLike | undefined = storage(),
  now = Date.now(),
): boolean {
  const key = keyFor(value.owner_id, value.order_id);
  const raw = JSON.stringify({
    ...value,
    expires_at: now + REPEAT_OPERATION_TTL,
  });
  memory.set(key, raw);
  try {
    if (!store) {
      memoryOnly.add(key);
      return false;
    }
    store.setItem(key, raw);
    memoryOnly.delete(key);
    return true;
  } catch {
    memoryOnly.add(key);
    return false;
  }
}
export function clearRepeatOperation(
  owner: number,
  order: number,
  store: StorageLike | undefined = storage(),
): void {
  const key = keyFor(owner, order);
  memory.set(key, null);
  memoryOnly.add(key);
  try {
    store?.removeItem(key);
  } catch {
    /* Tombstone keeps an earlier operation from returning. */
  }
}

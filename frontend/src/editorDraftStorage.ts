type DraftStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const TTL = 24 * 60 * 60 * 1000;
const fallbackStorage: DraftStorage = {
  getItem: () => null,
  setItem: () => {
    throw new Error("Session storage is unavailable.");
  },
  removeItem: () => undefined,
};
const memory = new WeakMap<
  DraftStorage,
  Map<string, { raw: string; persistent: boolean }>
>();
const removed = new WeakMap<DraftStorage, Set<string>>();
const listeners = new Set<() => void>();
function drafts(store: DraftStorage) {
  let items = memory.get(store);
  if (!items) {
    items = new Map();
    memory.set(store, items);
  }
  return items;
}
function notify() {
  listeners.forEach((listener) => listener());
}
export function subscribeEditorDrafts(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
export function hasMemoryOnlyEditorDrafts(
  store: DraftStorage,
  prefix: string,
): boolean {
  return [...drafts(store)].some(
    ([key, value]) =>
      (key === prefix || key.startsWith(`${prefix}:`)) && !value.persistent,
  );
}
export function editorDraftStorage(): DraftStorage {
  try {
    return window.sessionStorage;
  } catch {
    return fallbackStorage;
  }
}

export function editorDraftKey(
  userId: number,
  productId: number | null,
): string {
  return `pitomo:editor-draft:v1:${userId}:${productId ?? "new"}`;
}
export function saveEditorDraft(
  store: DraftStorage,
  key: string,
  data: unknown,
  now = Date.now(),
): boolean {
  const raw = JSON.stringify({ savedAt: now, data });
  removed.get(store)?.delete(key);
  drafts(store).set(key, { raw, persistent: false });
  try {
    store.setItem(key, raw);
    drafts(store).set(key, { raw, persistent: true });
    notify();
    return true;
  } catch {
    notify();
    return false;
  }
}
export function loadEditorDraft<T>(
  store: DraftStorage,
  key: string,
  valid: (value: unknown) => value is T,
  now = Date.now(),
): T | null {
  try {
    if (removed.get(store)?.has(key)) return null;
    const raw = drafts(store).get(key)?.raw ?? store.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (
      !Number.isFinite(parsed.savedAt) ||
      now - parsed.savedAt > TTL ||
      parsed.savedAt > now ||
      !valid(parsed.data)
    ) {
      removeEditorDraft(store, key, false);
      return null;
    }
    return parsed.data;
  } catch {
    return null;
  }
}
export function removeEditorDraft(
  store: DraftStorage,
  key: string,
  notifyChange = true,
): void {
  drafts(store).delete(key);
  let keys = removed.get(store);
  if (!keys) {
    keys = new Set();
    removed.set(store, keys);
  }
  keys.add(key);
  try {
    store.removeItem(key);
  } catch {
    /* Storage may be disabled. */
  }
  if (notifyChange) notify();
}

import { describe, expect, it } from "vitest";
import {
  loadEditorDraft,
  saveEditorDraft,
  editorDraftKey,
  hasMemoryOnlyEditorDrafts,
  removeEditorDraft,
} from "./editorDraftStorage";

function storage() {
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
}
const valid = (value: unknown): value is { name: string } =>
  Boolean(value && typeof (value as { name?: unknown }).name === "string");
describe("admin editor drafts", () => {
  it("restores unsaved text only for the same user and product", () => {
    const store = storage();
    const key = editorDraftKey(1, 2);
    saveEditorDraft(store, key, { name: "Unsaved" }, 100);
    expect(loadEditorDraft(store, key, valid, 200)).toEqual({
      name: "Unsaved",
    });
    expect(loadEditorDraft(store, editorDraftKey(2, 2), valid, 200)).toBeNull();
    expect(loadEditorDraft(store, editorDraftKey(1, 3), valid, 200)).toBeNull();
  });
  it("discards expired, malformed and wrong-shape data", () => {
    const store = storage();
    saveEditorDraft(store, "draft", { name: "Old" }, 0);
    expect(loadEditorDraft(store, "draft", valid, 86_400_001)).toBeNull();
    store.setItem("draft", "bad json");
    expect(loadEditorDraft(store, "draft", valid, 100)).toBeNull();
    saveEditorDraft(store, "draft", { price: "100" }, 100);
    expect(loadEditorDraft(store, "draft", valid, 100)).toBeNull();
  });
  it("restores a same-tab draft after QuotaExceededError even if persistent data is missing or malformed", () => {
    let raw: string | null = null;
    const store = {
      getItem: () => raw,
      setItem: () => {
        throw new DOMException("Full", "QuotaExceededError");
      },
      removeItem: () => {
        raw = null;
      },
    };
    expect(saveEditorDraft(store, "draft", { name: "Keep me" }, 100)).toBe(
      false,
    );
    expect(loadEditorDraft(store, "draft", valid, 101)).toEqual({
      name: "Keep me",
    });
    raw = "broken persistent JSON";
    expect(loadEditorDraft(store, "draft", valid, 102)).toEqual({
      name: "Keep me",
    });
    expect(hasMemoryOnlyEditorDrafts(store, "draft")).toBe(true);
    removeEditorDraft(store, "draft");
    expect(loadEditorDraft(store, "draft", valid, 103)).toBeNull();
    expect(hasMemoryOnlyEditorDrafts(store, "draft")).toBe(false);
  });
  it("clears a memory-only warning after persistence recovers and covers variant drafts", () => {
    const store = storage();
    const set = store.setItem;
    store.setItem = () => {
      throw new Error("full");
    };
    saveEditorDraft(store, "product:variant:1", { name: "Variant" }, 100);
    expect(hasMemoryOnlyEditorDrafts(store, "product")).toBe(true);
    store.setItem = set;
    expect(
      saveEditorDraft(store, "product:variant:1", { name: "Variant" }, 101),
    ).toBe(true);
    expect(hasMemoryOnlyEditorDrafts(store, "product")).toBe(false);
  });
  it("fails safely when browser storage is unavailable", () => {
    const store = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("quota");
      },
      removeItem: () => undefined,
    };
    expect(() =>
      saveEditorDraft(store, "draft", { name: "x" }, 100),
    ).not.toThrow();
    expect(loadEditorDraft(store, "draft", valid, 100)).toEqual({ name: "x" });
  });
});

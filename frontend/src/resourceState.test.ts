import { describe, expect, it } from "vitest";
import { beginResourceRequest, resourceView } from "./resourceState";

const loaded = { path: "/orders/1", dataPath: "/orders/1", data: { id: 1 }, error: "", pending: false };

describe("resource refresh and scope boundaries", () => {
  it("never retains data across users even for the same URL and explicit previous-data mode", () => {
    const owned = { ...loaded, scope: 7 };
    expect(resourceView(owned, loaded.path, true, 8)).toMatchObject({ data: null, loading: true });
    expect(beginResourceRequest(owned, loaded.path, true, 8).data).toBeNull();
  });
  it("keeps a loaded review/order visible during same-path refresh", () => {
    const next = beginResourceRequest(loaded, loaded.path);
    expect(resourceView(next, loaded.path)).toMatchObject({ data: { id: 1 }, loading: false, refreshing: true });
  });
  it("never reveals previous private data on a different path, even before its effect runs", () => {
    expect(resourceView(loaded, "/orders/2")).toMatchObject({ data: null, loading: true, refreshing: false });
    expect(beginResourceRequest(loaded, "/orders/2").data).toBeNull();
  });
  it("clears data immediately when authentication disables the request", () => {
    expect(resourceView(loaded, null)).toMatchObject({ data: null, loading: false, refreshing: false });
  });
  it("allows an explicitly public catalog to retain results and identifies their original query", () => {
    const next = beginResourceRequest(loaded, "/products?min_price=2500", true);
    expect(resourceView(next, next.path, true)).toMatchObject({ data: { id: 1 }, dataPath: "/orders/1", refreshing: true });
  });
  it("retains the last successful snapshot with a refresh error so a retry remains possible", () => {
    expect(resourceView({ ...loaded, error: "offline" }, loaded.path)).toMatchObject({ data: { id: 1 }, error: "offline", loading: false });
  });
});

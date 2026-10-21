import { describe, expect, it } from "vitest";
import { adminPage, orderFilters, orderQuery } from "./adminFilters";
import { exportPath } from "./exports";

describe("admin queue links and export parity", () => {
  it("restores a page from the URL and rejects invalid page values", () => {
    expect(adminPage(new URLSearchParams("page=3"))).toBe(3);
    expect(adminPage(new URLSearchParams("page=-1"))).toBe(1);
    expect(adminPage(new URLSearchParams("page=NaN"))).toBe(1);
  });
  it("preserves a delivery queue and filter in both API and exported records", () => {
    const filters = orderFilters(new URLSearchParams("queue=incidents&delivery_incident=engine_failure&received=false&stale_hours=24"));
    const api = new URLSearchParams(orderQuery(filters, 2));
    const download = new URLSearchParams(exportPath("orders", { ...filters, format: "xlsx" }).split("?")[1]);
    for (const key of ["queue", "delivery_incident", "received", "stale_hours"]) expect(download.get(key)).toBe(api.get(key));
    expect(api.get("offset")).toBe("20");
    expect(api.get("received")).toBe("false");
  });
  it("ignores invalid enum filters from pasted links", () => expect(orderFilters(new URLSearchParams("queue=bogus&delivery_stage=xyz"))).toEqual({}));
  it("carries the low-stock threshold into a product export", () => expect(exportPath("products", { format: "xlsx", stock_max: 5 })).toContain("stock_max=5"));
});

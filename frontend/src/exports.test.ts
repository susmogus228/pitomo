import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { exportFilename, exportPath, fetchExport, saveExport } from "./exports";

describe("server-side analytics export", () => {
  const fetchMock = vi.fn();
  const dispatch = vi.fn();
  beforeEach(() => { vi.stubGlobal("fetch", fetchMock); vi.stubGlobal("window", { dispatchEvent: dispatch }); fetchMock.mockReset(); dispatch.mockReset(); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("passes active filters and dates without limiting the download to the visible page", () => {
    const query = new URL(exportPath("orders", { format: "xlsx", status: "created", payment_status: "demo_paid", delivery_method: "delivery", date_from: "2026-10-01", date_to: "2026-10-05" }), "https://example.test");
    expect(Object.fromEntries(query.searchParams)).toEqual({ format: "xlsx", date_from: "2026-10-01", date_to: "2026-10-05", status: "created", payment_status: "demo_paid", delivery_method: "delivery", include_contacts: "false" });
    expect(query.searchParams.has("limit")).toBe(false);
    expect(query.searchParams.has("offset")).toBe(false);
    expect(exportPath("reviews", { format: "csv", unanswered_only: true, include_contacts: true })).toBe("/admin/exports/reviews?format=csv&unanswered_only=true");
  });
  it("downloads a binary response using protected same-origin cookies and the server filename", async () => {
    fetchMock.mockResolvedValue(new Response(new Uint8Array([80, 75, 3, 4]), { headers: { "Content-Disposition": "attachment; filename*=UTF-8''%D0%97%D0%B0%D0%BA%D0%B0%D0%B7%D1%8B.xlsx" } }));
    const file = await fetchExport("orders", { format: "xlsx", include_contacts: true });
    expect(file.filename).toBe("Заказы.xlsx");
    expect(await file.blob.arrayBuffer()).toEqual(new Uint8Array([80, 75, 3, 4]).buffer);
    expect(fetchMock.mock.calls[0][1].credentials).toBe("same-origin");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/admin/exports/orders?format=xlsx&include_contacts=true");
  });
  it("uses ZIP as fallback for multi-table CSV exports", async () => {
    fetchMock.mockResolvedValue(new Response("zip"));
    expect((await fetchExport("all", { format: "csv" })).filename).toBe("pitomo-all.zip");
  });
  it("reports a denied export and clears an expired session instead of saving an error page", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "Доступ запрещён" }), { status: 403 }));
    await expect(fetchExport("users", { format: "xlsx" })).rejects.toMatchObject({ status: 403, message: "Доступ запрещён" });
    expect(dispatch).not.toHaveBeenCalled();
    fetchMock.mockResolvedValue(new Response("{}", { status: 401 }));
    await expect(fetchExport("users", { format: "xlsx" })).rejects.toMatchObject({ status: 401 });
    expect(dispatch.mock.calls[0][0].type).toBe("pitomo:session-expired");
  });
  it("sanitizes download filenames and handles invalid encoded headers", () => {
    expect(exportFilename('attachment; filename="../orders.csv"', "fallback.csv")).toBe(".._orders.csv");
    expect(exportFilename("attachment; filename=orders.csv; filename*=UTF-8''%wrong", "fallback.csv")).toBe("orders.csv");
  });
  it("starts a browser download and releases its temporary URL", () => {
    const link = { href: "", download: "", click: vi.fn(), remove: vi.fn() };
    const appendChild = vi.fn();
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:export");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.stubGlobal("document", { createElement: () => link, body: { appendChild } });
    vi.stubGlobal("window", { setTimeout: (callback: () => void) => { callback(); return 1; } });
    const blob = new Blob(["report"]);
    saveExport(blob, "orders.xlsx");
    expect(create).toHaveBeenCalledWith(blob);
    expect(link.download).toBe("orders.xlsx");
    expect(link.click).toHaveBeenCalledOnce();
    expect(link.remove).toHaveBeenCalledOnce();
    expect(revoke).toHaveBeenCalledWith("blob:export");
  });
});

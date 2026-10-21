import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, errorMessage, readCookie } from "./api";

describe("browser API boundary", () => {
  const fetchMock = vi.fn();
  const dispatch = vi.fn();
  beforeEach(() => {
    vi.stubGlobal("document", {
      cookie: "other=value; pitomo_csrf=csrf%2Btoken",
    });
    vi.stubGlobal("window", { dispatchEvent: dispatch });
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
    dispatch.mockReset();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("sends CSRF and same-origin credentials on mutation without exposing a bearer token", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ id: 17 }), { status: 201 }),
    );
    expect(
      await api("/orders", {
        method: "POST",
        headers: { "Idempotency-Key": "stable-key" },
        body: "{}",
      }),
    ).toEqual({ id: 17 });
    const [url, request] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/orders");
    expect(request.credentials).toBe("same-origin");
    expect(request.headers.get("X-CSRF-Token")).toBe("csrf+token");
    expect(request.headers.get("Idempotency-Key")).toBe("stable-key");
    expect(request.headers.has("Authorization")).toBe(false);
  });
  it("does not attach CSRF or JSON headers to a GET", async () => {
    fetchMock.mockResolvedValue(new Response("[]"));
    await api("/products");
    expect(fetchMock.mock.calls[0][1].headers.has("X-CSRF-Token")).toBe(false);
    expect(fetchMock.mock.calls[0][1].headers.has("Content-Type")).toBe(false);
  });
  it("lets the browser set the multipart boundary while retaining CSRF on photo uploads", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ id: 1, url: "/media/reviews/photo.webp" }), { status: 201 }));
    const body = new FormData();
    body.set("file", new Blob(["image"], { type: "image/webp" }), "photo.webp");
    await api("/products/1/reviews/2/photos", { method: "POST", body });
    const request = fetchMock.mock.calls[0][1];
    expect(request.body).toBe(body);
    expect(request.headers.has("Content-Type")).toBe(false);
    expect(request.headers.get("X-CSRF-Token")).toBe("csrf+token");
  });
  it("accepts 204 responses without trying to parse JSON", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    expect(await api("/cart/items/1", { method: "DELETE" })).toBeUndefined();
  });
  it("clears an expired protected session and preserves backend error text", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Сессия истекла" }), {
        status: 401,
      }),
    );
    await expect(api("/cart")).rejects.toMatchObject({
      status: 401,
      message: "Сессия истекла",
    });
    expect(dispatch.mock.calls[0][0].type).toBe("pitomo:session-expired");
  });
  it("does not broadcast a session expiry for incorrect login credentials", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Неверный пароль" }), {
        status: 401,
      }),
    );
    await expect(
      api("/auth/browser/login", { method: "POST", body: "{}" }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(dispatch).not.toHaveBeenCalled();
  });
  it("reports connection failures without claiming a successful mutation", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(
      api("/orders", { method: "POST", body: "{}" }),
    ).rejects.toMatchObject({ status: 0 });
  });
  it("preserves aborts so unmounted requests stay quiet", async () => {
    const abort = new DOMException("Aborted", "AbortError");
    fetchMock.mockRejectedValue(abort);
    await expect(api("/products")).rejects.toBe(abort);
  });
});

describe("transport decoding", () => {
  it("reads only an exact cookie name and safely rejects malformed encoding", () => {
    expect(
      readCookie("pitomo_csrf", "not_pitomo_csrf=wrong; pitomo_csrf=right"),
    ).toBe("right");
    expect(readCookie("pitomo_csrf", "pitomo_csrf=%not-valid")).toBeUndefined();
    expect(readCookie("pitomo_csrf", "other=value")).toBeUndefined();
  });
  it("understands both documented validation and alternate structured error formats", () => {
    expect(
      errorMessage({
        detail: [
          { msg: "Value error, Некорректный email" },
          { msg: "Введите имя" },
        ],
      }),
    ).toBe("Некорректный email. Введите имя");
    expect(errorMessage({ error: { message: "Нет в наличии" } })).toBe(
      "Нет в наличии",
    );
    expect(errorMessage(null, "Fallback")).toBe("Fallback");
  });
});

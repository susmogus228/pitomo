import { describe, expect, it } from "vitest";
import { adminAccess } from "./adminAccess";
import type { User } from "./types";

const customer: User = { id: 1, email: "buyer@example.test", first_name: "Покупатель", last_name: null, role: "customer", is_active: true };

describe("admin route gate", () => {
  it("waits for the session before allowing any admin page to mount", () => {
    expect(adminAccess(null, true, "")).toBe("loading");
    expect(adminAccess(null, false, "Сеть недоступна")).toBe("error");
  });
  it("redirects visitors and blocks customers or disabled administrators", () => {
    expect(adminAccess(null, false, "")).toBe("login");
    expect(adminAccess(customer, false, "")).toBe("denied");
    expect(adminAccess({ ...customer, role: "admin", is_active: false }, false, "")).toBe("denied");
  });
  it("allows an active administrator", () => {
    expect(adminAccess({ ...customer, role: "admin" }, false, "")).toBe("allowed");
  });
});

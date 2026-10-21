import { describe, expect, it } from "vitest";
import {
  authFieldErrors,
  checkoutFieldErrors,
  focusFirstError,
} from "./formValidation";

describe("field-specific checkout and authentication validation", () => {
  const registration = {
    first_name: "Иван",
    email: "test@example.test",
    password: "StrongPass123",
    password_confirm: "StrongPass123",
    consent_name: "Тестовый Иван",
    service_consent: true,
  };
  it("identifies the password confirmation field before any request", () => {
    expect(
      authFieldErrors({ ...registration, password_confirm: "different" }, true),
    ).toEqual({ password_confirm: "Пароли не совпадают. Повторите пароль." });
  });
  it("associates required registration and consent problems with their own fields", () => {
    const errors = authFieldErrors(
      {
        ...registration,
        first_name: " ",
        email: "wrong",
        consent_name: "Иван",
        service_consent: false,
      },
      true,
    );
    expect(Object.keys(errors)).toEqual([
      "first_name",
      "email",
      "consent_name",
      "service_consent",
    ]);
  });
  it("does not require registration-only fields during login", () => {
    expect(
      authFieldErrors({ email: "test@example.test", password: "x" }, false),
    ).toEqual({});
  });
  const checkout = {
    contact_name: "Иван",
    phone: "+7 700 123 45 67",
    delivery_method: "delivery" as const,
    payment_method: "cod" as const,
    address: "Алматы, Абая, 10",
  };
  it("reports invalid phone and missing address separately", () => {
    expect(
      Object.keys(
        checkoutFieldErrors({ ...checkout, phone: "abc", address: "" }),
      ),
    ).toEqual(["phone", "address"]);
  });
  it("allows pickup without a delivery address", () => {
    expect(
      checkoutFieldErrors({
        ...checkout,
        delivery_method: "pickup",
        address: "",
      }),
    ).toEqual({});
  });
  it("rejects whitespace names and an oversized complete delivery address", () => {
    expect(
      Object.keys(
        checkoutFieldErrors({
          ...checkout,
          contact_name: "  ",
          address: "A".repeat(501),
        }),
      ),
    ).toEqual(["contact_name", "address"]);
  });
  it("focuses the first invalid control in form order rather than error insertion order", () => {
    const focused: string[] = [];
    const form = {
      elements: [
        { name: "contact_name", focus: () => focused.push("contact_name") },
        { name: "phone", focus: () => focused.push("phone") },
        { name: "address", focus: () => focused.push("address") },
      ],
    } as unknown as HTMLFormElement;
    focusFirstError(form, { address: "Missing", phone: "Invalid" });
    expect(focused).toEqual(["phone"]);
  });
});

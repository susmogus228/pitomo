import { describe, expect, it } from "vitest";
import {
  addressInput,
  savedAddressCheckout,
  savedAddressLine,
} from "./purchaseTypes";

describe("saved address checkout rendering", () => {
  const address = {
    label: "Дом",
    city: " Алматы ",
    street: "Абая",
    house: " 10 ",
    details: " кв. 24, подъезд 2 ",
    lat: 43,
    lon: 76,
    source: "manual" as const,
    is_default: false,
  };
  it("joins only the actual address fields without leaking account metadata", () => {
    expect(savedAddressLine(address)).toBe("Алматы, Абая, 10");
    expect(savedAddressCheckout(address)).toBe(
      "Алматы, Абая, 10, кв. 24, подъезд 2",
    );
  });
  it("does not append punctuation for empty optional details", () => {
    expect(savedAddressCheckout({ ...address, details: " " })).toBe(
      "Алматы, Абая, 10",
    );
  });
  it("does not submit server-owned identity and timestamps when editing", () => {
    const persisted = {
      ...address,
      id: 1,
      created_at: "2026-10-13",
      updated_at: "2026-10-13",
    };
    expect(addressInput(persisted)).toEqual(address);
    expect(Object.keys(addressInput(persisted))).not.toContain("id");
  });
});

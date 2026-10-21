import { describe, expect, it } from "vitest";
import { checkoutAddress, editAddress, kazakhstanAddresses, LatestAddressRequest, suggestionLocation } from "./address";

describe("address and delivery point consistency", () => {
  const address = { label: "Алматы, Абая, 10", lat: 43.238901234, lon: 76.889712345, country_code: "kz" };
  it("clears old coordinates whenever the buyer changes the address", () => {
    const selected = suggestionLocation(address);
    expect(selected.point).toEqual({ lat: 43.2389012, lon: 76.8897123 });
    expect(editAddress("Астана, Достык, 5")).toEqual({ address: "Астана, Достык, 5", point: null });
  });
  it("keeps apartment, entrance and floor separate while reverse lookup changes the base address", () => {
    const details = { apartment: " 24 ", entrance: "2", floor: "3" };
    expect(checkoutAddress(address.label, details)).toBe("Алматы, Абая, 10, кв. 24, подъезд 2, этаж 3");
    expect(checkoutAddress("Астана, Достык, 5", details)).toBe("Астана, Достык, 5, кв. 24, подъезд 2, этаж 3");
    expect(checkoutAddress(" Дом 10 ", { apartment: "", entrance: "", floor: "" })).toBe("Дом 10");
  });
  it("rejects suggestions from other countries or with invalid points", () => {
    expect(kazakhstanAddresses([address, { ...address, country_code: "ru" }, { ...address, lat: NaN }, { ...address, label: "" }])).toEqual([address]);
  });
  it("ignores an earlier request even if a transport resolves after cancellation", async () => {
    const requests = new LatestAddressRequest();
    const first = requests.start();
    const second = requests.start();
    const replies: string[] = [];
    await Promise.all([
      Promise.resolve().then(() => { if (first.current()) replies.push("old address"); }),
      Promise.resolve().then(() => { if (second.current()) replies.push("new address"); }),
    ]);
    expect(first.signal.aborted).toBe(true);
    expect(replies).toEqual(["new address"]);
    requests.cancel();
    expect(second.current()).toBe(false);
  });
});

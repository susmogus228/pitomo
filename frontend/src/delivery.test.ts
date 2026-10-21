import { describe, expect, it } from "vitest";
import { canCancelOrder, canReceiveOrder, isDeliveryMoving, nextDeliveryStage } from "./delivery";
import type { Order } from "./types";

const base: Order = {
  id: 1, user_id: 2, status: "created", created_at: "2026-10-13T00:00:00Z",
  items: [], total_items: 0, total: "0", currency: "KZT", contact_name: "Test",
  phone: "+77000000000", address: "Test address", comment: null,
  delivery_method: "delivery", payment_method: "cod", payment_status: "cod_pending",
  is_demo: false, delivery_tracking: {
    stage: "warehouse", incident: null, incident_note: null, updated_at: null,
    version: 0, history: [],
  },
};
const order = (patch: Partial<Order> = {}, tracking = {}) => ({
  ...base, ...patch, delivery_tracking: { ...base.delivery_tracking!, ...tracking },
});

describe("delivery action eligibility", () => {
  it("allows receipt only nearby without an incident", () => {
    expect(canReceiveOrder(order())).toBe(false);
    expect(canReceiveOrder(order({}, { stage: "in_transit" }))).toBe(false);
    expect(canReceiveOrder(order({}, { stage: "nearby" }))).toBe(true);
    for (const incident of ["flat_tire", "overturned", "engine_failure"])
      expect(canReceiveOrder(order({}, { stage: "nearby", incident }))).toBe(false);
  });
  it("preserves pickup receipt and blocks unpaid or terminal orders", () => {
    expect(canReceiveOrder({ ...base, delivery_method: "pickup", delivery_tracking: null })).toBe(true);
    for (const patch of [
      { payment_status: "failed" as const }, { status: "cancelled" as const },
      { received_at: "2026-10-13T01:00:00Z" },
    ]) expect(canReceiveOrder(order(patch, { stage: "nearby" }))).toBe(false);
  });
  it("forbids stock-return cancellation after shipping or payment", () => {
    expect(canCancelOrder(order())).toBe(true);
    expect(canCancelOrder(order({}, { stage: "in_transit" }))).toBe(false);
    expect(canCancelOrder(order({}, { stage: "nearby" }))).toBe(false);
    expect(canCancelOrder(order({ payment_status: "demo_paid" }))).toBe(false);
    expect(canCancelOrder(order({ received_at: "2026-10-13T01:00:00Z" }))).toBe(false);
  });
  it("moves only while delivering, without incident and before completion", () => {
    expect(isDeliveryMoving(order())).toBe(false);
    expect(isDeliveryMoving(order({}, { stage: "in_transit" }))).toBe(true);
    expect(isDeliveryMoving(order({}, { stage: "nearby" }))).toBe(true);
    expect(isDeliveryMoving(order({}, { stage: "in_transit", incident: "flat_tire" }))).toBe(false);
    expect(isDeliveryMoving(order({}, { stage: "in_transit", incident: "engine_failure" }))).toBe(false);
    expect(isDeliveryMoving(order({ status: "cancelled" }, { stage: "in_transit" }))).toBe(false);
    expect(isDeliveryMoving(order({ received_at: "2026-10-13T01:00:00Z" }, { stage: "nearby" }))).toBe(false);
  });
  it("provides exactly two forward transitions", () => {
    expect(nextDeliveryStage("warehouse")).toBe("in_transit");
    expect(nextDeliveryStage("in_transit")).toBe("nearby");
    expect(nextDeliveryStage("nearby")).toBe(null);
  });
});

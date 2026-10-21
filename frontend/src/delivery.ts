import type { DeliveryStage, Order } from "./types";

export const deliveryStages: { id: DeliveryStage; label: string }[] = [
  { id: "warehouse", label: "На складе" },
  { id: "in_transit", label: "В пути" },
  { id: "nearby", label: "Рядом с вами" },
];
export const incidentLabels = {
  flat_tire: "Проколота шина",
  overturned: "Грузовик перевернулся",
  engine_failure: "Проблема с двигателем",
};
export function isOrderTerminal(order: Order) {
  return order.status === "cancelled" || order.payment_status === "cancelled" || Boolean(order.received_at);
}
export function isPaymentReady(order: Order) {
  return order.payment_status === "demo_paid" || order.payment_status === "cod_pending";
}
export function canReceiveOrder(order: Order) {
  return !isOrderTerminal(order) && isPaymentReady(order) && (
    order.delivery_method === "pickup" || (
      order.delivery_tracking?.stage === "nearby" && !order.delivery_tracking.incident
    )
  );
}
export function canCancelOrder(order: Order) {
  return !isOrderTerminal(order) && order.payment_status !== "demo_paid" && (
    order.delivery_method === "pickup" || order.delivery_tracking?.stage === "warehouse"
  );
}
export function nextDeliveryStage(stage: DeliveryStage): DeliveryStage | null {
  return deliveryStages[deliveryStages.findIndex((item) => item.id === stage) + 1]?.id ?? null;
}
export function isDeliveryMoving(order: Order) {
  return !isOrderTerminal(order) && isPaymentReady(order) && Boolean(order.delivery_tracking) &&
    order.delivery_tracking!.stage !== "warehouse" && !order.delivery_tracking!.incident;
}

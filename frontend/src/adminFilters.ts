export const ORDER_QUEUES = [
  ["active", "Все активные"], ["warehouse", "Нужно отправить"],
  ["in_transit", "В пути"], ["incidents", "Проблемы доставки"],
  ["awaiting_receipt", "Ожидают получения"], ["received", "Получены"],
] as const;

export function adminPage(params: URLSearchParams) {
  const value = Number(params.get("page") || 1);
  return Number.isSafeInteger(value) && value >= 1 && value <= 40_000_000 ? value : 1;
}

export interface OrderFilters {
  status?: string;
  payment_status?: string;
  delivery_method?: string;
  delivery_stage?: string;
  delivery_incident?: string;
  queue?: string;
  received?: boolean;
  stale_hours?: number;
}

export function orderFilters(params: URLSearchParams): OrderFilters {
  const result: Record<string, string | boolean | number> = {};
  const enums: Record<string, readonly string[]> = {
    status: ["created", "cancelled"], payment_status: ["pending", "demo_paid", "failed", "cod_pending", "cancelled"],
    delivery_method: ["pickup", "delivery"], delivery_stage: ["warehouse", "in_transit", "nearby"],
    delivery_incident: ["flat_tire", "overturned", "engine_failure"], queue: ORDER_QUEUES.map(([id]) => id),
  };
  for (const [key, values] of Object.entries(enums)) {
    const value = params.get(key);
    if (value && values.includes(value)) result[key] = value;
  }
  const received = params.get("received");
  if (received === "true" || received === "false") result.received = received === "true";
  const hours = Number(params.get("stale_hours"));
  if (Number.isInteger(hours) && hours >= 1 && hours <= 8760) result.stale_hours = hours;
  return result;
}

export function orderQuery(filters: OrderFilters, page: number, limit = 20) {
  const query = new URLSearchParams({ limit: String(limit), offset: String((page - 1) * limit) });
  for (const [key, value] of Object.entries(filters)) if (value !== undefined) query.set(key, String(value));
  return query.toString();
}

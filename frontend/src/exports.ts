import { ApiError, errorMessage } from "./api";

export type ExportDataset = "overview" | "orders" | "products" | "replenishments" | "users" | "reviews" | "discounts" | "all";
export type ExportFormat = "xlsx" | "csv";
export interface ExportOptions {
  format: ExportFormat;
  date_from?: string;
  date_to?: string;
  q?: string;
  status?: string;
  payment_status?: string;
  delivery_method?: string;
  delivery_stage?: string;
  delivery_incident?: string;
  queue?: string;
  received?: boolean;
  stale_hours?: number;
  stock_max?: number;
  unanswered_only?: boolean;
  visibility?: "all" | "visible" | "hidden";
  include_contacts?: boolean;
}

export function exportPath(dataset: ExportDataset, options: ExportOptions): string {
  const query = new URLSearchParams({ format: options.format });
  for (const field of ["date_from", "date_to", "q", "status", "payment_status", "delivery_method", "delivery_stage", "delivery_incident", "queue", "visibility"] as const) {
    if (options[field]) query.set(field, options[field]);
  }
  for (const field of ["received", "stale_hours", "stock_max"] as const) if (options[field] !== undefined) query.set(field, String(options[field]));
  if (options.unanswered_only) query.set("unanswered_only", "true");
  if (["orders", "users", "all"].includes(dataset)) query.set("include_contacts", String(options.include_contacts === true));
  return `/admin/exports/${dataset}?${query}`;
}

export function exportFilename(disposition: string | null, fallback: string): string {
  const encoded = disposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = disposition?.match(/filename="([^"]+)"|filename=([^;]+)/i);
  let name = plain?.[1] || plain?.[2]?.trim() || fallback;
  if (encoded) { try { name = decodeURIComponent(encoded.trim()); } catch { /* Use the plain filename. */ } }
  return name.replace(/[\\/\u0000-\u001f\u007f]/g, "_").slice(0, 180) || fallback;
}

export async function fetchExport(dataset: ExportDataset, options: ExportOptions, signal?: AbortSignal): Promise<{ blob: Blob; filename: string }> {
  let response: Response;
  try { response = await fetch(`/api/v1${exportPath(dataset, options)}`, { credentials: "same-origin", signal }); }
  catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "Нет связи с магазином. Повторите выгрузку после восстановления подключения.");
  }
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("pitomo:session-expired"));
    const payload: unknown = await response.json().catch(() => null);
    throw new ApiError(response.status, errorMessage(payload, "Не удалось подготовить выгрузку. Попробуйте ещё раз."));
  }
  const extension = options.format === "csv" && ["orders", "all"].includes(dataset) ? "zip" : options.format;
  return { blob: await response.blob(), filename: exportFilename(response.headers.get("Content-Disposition"), `pitomo-${dataset}.${extension}`) };
}

export function saveExport(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

import type { Cart } from "./types";

export interface AddressInput {
  label: string;
  city: string;
  street: string;
  house: string;
  details: string;
  lat: number | null;
  lon: number | null;
  source: "manual" | "geoapify" | "map" | "geolocation";
  is_default: boolean;
}
export interface SavedAddress extends AddressInput {
  id: number;
  created_at: string;
  updated_at: string;
}
export interface AddressPage {
  items: SavedAddress[];
  limit: number;
}
export function addressInput(value: AddressInput): AddressInput {
  return {
    label: value.label,
    city: value.city,
    street: value.street,
    house: value.house,
    details: value.details,
    lat: value.lat,
    lon: value.lon,
    source: value.source,
    is_default: value.is_default,
  };
}
export interface CartMergeItem {
  variant_id: number;
  requested_quantity: number;
  added_quantity: number;
  remaining_quantity: number;
  status: "added" | "reduced" | "out_of_stock" | "missing";
  message: string;
}
export interface CartMergeResult {
  cart: Cart;
  items: CartMergeItem[];
  replayed: boolean;
}
export interface RepeatItem {
  variant_id: number;
  product_id: number;
  product_name: string;
  label: string;
  sku: string;
  image_url: string | null;
  ordered_quantity: number;
  existing_quantity: number;
  add_quantity: number;
  available_stock: number;
  previous_unit_price: string;
  unit_price: string | null;
  original_unit_price: string | null;
  status: "available" | "reduced" | "out_of_stock" | "missing";
  changes: string[];
  line_total: string;
}
export interface RepeatPreview {
  order_id: number;
  fingerprint: string;
  items: RepeatItem[];
  subtotal: string;
  currency: "KZT";
  can_repeat: boolean;
}
export interface RepeatResult {
  cart: Cart;
  items: RepeatItem[];
  replayed: boolean;
}

export const savedAddressLine = (
  address: Pick<AddressInput, "city" | "street" | "house">,
) =>
  [address.city, address.street, address.house]
    .map((value) => value.trim())
    .filter(Boolean)
    .join(", ");
export const savedAddressCheckout = (address: AddressInput) =>
  [savedAddressLine(address), address.details.trim()]
    .filter(Boolean)
    .join(", ");
export const operationKey = () => crypto.randomUUID();

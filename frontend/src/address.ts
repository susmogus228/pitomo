import type { GeoPoint } from "./geo";
import { roundedPoint, validPoint } from "./geo";

export interface GeoConfig { enabled: boolean; country_code: "kz" }
export interface AddressSuggestion extends GeoPoint {
  label: string;
  country_code: string;
  city?: string | null;
  street?: string | null;
  housenumber?: string | null;
  postcode?: string | null;
}
export interface AddressLocation { address: string; point: GeoPoint | null }
export interface AddressDetails { apartment: string; entrance: string; floor: string }

export function editAddress(value: string): AddressLocation { return { address: value, point: null }; }
export function suggestionLocation(item: AddressSuggestion): AddressLocation { return { address: item.label, point: roundedPoint(item) }; }
export function kazakhstanAddresses(items: AddressSuggestion[]): AddressSuggestion[] {
  return items.filter((item) => item.country_code.toLowerCase() === "kz" && item.label.trim() && validPoint(item));
}
export function checkoutAddress(base: string, details: AddressDetails): string {
  return [base.trim(), details.apartment.trim() && `кв. ${details.apartment.trim()}`, details.entrance.trim() && `подъезд ${details.entrance.trim()}`, details.floor.trim() && `этаж ${details.floor.trim()}`].filter(Boolean).join(", ");
}

export class LatestAddressRequest {
  private revision = 0;
  private controller: AbortController | null = null;
  cancel(): void { this.revision += 1; this.controller?.abort(); this.controller = null; }
  start(): { signal: AbortSignal; current: () => boolean } {
    this.cancel();
    const revision = this.revision;
    const controller = new AbortController();
    this.controller = controller;
    return { signal: controller.signal, current: () => this.revision === revision && !controller.signal.aborted };
  }
}

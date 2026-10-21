export type PetType =
  | "cat"
  | "dog"
  | "bird"
  | "small_pet"
  | "fish"
  | "reptile"
  | "amphibian"
  | "invertebrate";
export interface Variant {
  id: number;
  sku: string;
  label: string;
  price: string;
  original_price?: string | null;
  discount_percent?: number | null;
  currency: "KZT";
  stock: number;
}
export interface Product {
  id: number;
  name: string;
  pet_type: PetType;
  brand: string;
  category: "food" | "accessory";
  description: string;
  composition?: string | null;
  material?: string | null;
  variants: Variant[];
  image_url?: string | null;
  images?: { id: number; url: string }[];
  product_kind?: ProductKind | null;
  is_hit?: boolean;
  discount_percent?: number | null;
  discount_start_at?: string | null;
  discount_end_at?: string | null;
  rating_average?: number | null;
  rating_count?: number;
}
export type ProductKind =
  | "food"
  | "treats"
  | "toys"
  | "bowls"
  | "litter"
  | "habitats"
  | "walking"
  | "care"
  | "aquatics"
  | "terrariums";
export interface ProductKindCount {
  id: ProductKind;
  name: string;
  count: number;
}
export interface ProductPage {
  items: Product[];
  total: number;
  page: number;
  page_size: number;
}
export interface User {
  id: number;
  email: string;
  first_name: string;
  last_name: string | null;
  role: string;
  is_active: boolean;
}
export interface CartItem {
  product_id: number;
  product_name: string;
  image_url?: string | null;
  variant_id: number;
  sku: string;
  label: string;
  unit_price: string;
  original_unit_price?: string | null;
  currency: string;
  quantity: number;
  available_stock: number;
  is_available: boolean;
  line_total: string;
}
export interface Cart {
  user_id: number;
  items: CartItem[];
  total_items: number;
  subtotal: string;
  currency: string;
  can_checkout: boolean;
}
export interface OrderItem {
  product_id: number;
  product_name: string;
  variant_id: number;
  sku: string;
  variant_label: string;
  unit_price: string;
  original_unit_price?: string | null;
  currency: string;
  quantity: number;
  line_total: string;
}
export interface CheckoutInput {
  contact_name: string;
  phone: string;
  delivery_method: "pickup" | "delivery";
  address?: string;
  delivery_lat?: number;
  delivery_lon?: number;
  comment?: string;
  payment_method: "demo" | "cod";
}
export type DeliveryStage = "warehouse" | "in_transit" | "nearby";
export type DeliveryIncident = "flat_tire" | "overturned" | "engine_failure";
export interface DeliveryTrackingState {
  stage: DeliveryStage;
  incident: DeliveryIncident | null;
  incident_note: string | null;
  updated_at: string | null;
  version: number;
  history: {
    event_type: "created" | "stage_changed" | "incident_reported" | "incident_resolved";
    stage: DeliveryStage;
    incident: DeliveryIncident | null;
    note: string | null;
    occurred_at: string;
  }[];
}
export type DeliveryCommand = { expected_version: number } & (
  | { stage: DeliveryStage; incident?: never; incident_note?: never }
  | { incident: DeliveryIncident | null; incident_note?: string | null; stage?: never }
);
export interface Order extends Omit<
  CheckoutInput,
  "contact_name" | "phone" | "address" | "comment" | "delivery_lat" | "delivery_lon"
> {
  id: number;
  user_id: number;
  status: "created" | "cancelled";
  created_at: string;
  items: OrderItem[];
  total_items: number;
  total: string;
  currency: string;
  contact_name: string | null;
  phone: string | null;
  address: string | null;
  delivery_lat?: string | null;
  delivery_lon?: string | null;
  received_at?: string | null;
  paid_at?: string | null;
  comment: string | null;
  is_demo: boolean;
  delivery_tracking: DeliveryTrackingState | null;
  payment_status:
    "pending" | "demo_paid" | "failed" | "cod_pending" | "cancelled";
}
export interface AdminOrder extends Order {
  customer_email: string;
  customer_first_name: string;
}
export interface AdminOrderPage {
  items: AdminOrder[];
  total: number;
  limit: number;
  offset: number;
}
export interface Review {
  id: number;
  author_id: number;
  rating: number;
  body: string;
  created_at: string;
  updated_at?: string | null;
  author_name: string;
  is_deleted: boolean;
  verified_purchase?: boolean;
  is_edited?: boolean;
  edited_at?: string | null;
  is_hidden?: boolean;
  photos: ReviewPhoto[];
  replies: ReviewReply[];
}
export interface ReviewPhoto { id: number; url: string }
export interface ReviewReply {
  id: number;
  parent_reply_id: number | null;
  author_id: number;
  author_name: string;
  body: string;
  created_at: string;
  updated_at?: string | null;
  is_official: boolean;
  is_pinned: boolean;
  is_deleted: boolean;
  is_edited?: boolean;
  edited_at?: string | null;
  photos: ReviewPhoto[];
}
export interface ReviewPage {
  items: Review[];
  total: number;
  average_rating: number | null;
  summary_total?: number;
  rating_distribution?: Record<string, number>;
}
export interface VetClinic {
  id: string | number;
  name: string;
  lat: number;
  lon: number;
  distance_m: number;
  address?: string | null;
  phone?: string | null;
  website?: string | null;
  emergency?: boolean | null;
  opening_hours?: string | null;
  osm_url?: string | null;
}
export interface NearbyVets {
  items: VetClinic[];
}
export interface StorefrontConfig {
  demo_payments_enabled: boolean;
  currency: "KZT";
}

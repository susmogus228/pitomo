export type ReviewSort = "newest" | "oldest" | "rating_desc" | "rating_asc";
export interface ReviewFilters {
  page: number;
  sort: ReviewSort;
  rating: string;
  withPhotos: boolean;
}
const sorts: ReviewSort[] = ["newest", "oldest", "rating_desc", "rating_asc"];
export function readReviewFilters(params: URLSearchParams): ReviewFilters {
  const value = params.get("reviews_page") || "1";
  const page = /^\d{1,9}$/.test(value)
    ? Math.max(1, Math.min(429496729, Number(value)))
    : 1;
  const sort = params.get("review_sort") as ReviewSort;
  const rating = params.get("review_rating") || "";
  return {
    page,
    sort: sorts.includes(sort) ? sort : "newest",
    rating: /^[1-5]$/.test(rating) ? rating : "",
    withPhotos: params.get("review_photos") === "true",
  };
}
export function updateReviewFilters(
  params: URLSearchParams,
  updates: Partial<ReviewFilters>,
): URLSearchParams {
  const current = { ...readReviewFilters(params), ...updates };
  if (updates.page === undefined) current.page = 1;
  const next = new URLSearchParams(params);
  for (const [key, value] of Object.entries({
    reviews_page: current.page > 1 ? String(current.page) : "",
    review_sort: current.sort === "newest" ? "" : current.sort,
    review_rating: current.rating,
    review_photos: current.withPhotos ? "true" : "",
  })) {
    if (value) next.set(key, value);
    else next.delete(key);
  }
  return next;
}
export function reviewApiQuery(filters: ReviewFilters): string {
  const query = new URLSearchParams({
    limit: "5",
    offset: String((filters.page - 1) * 5),
    sort: filters.sort,
    with_photos: String(filters.withPhotos),
  });
  if (filters.rating) query.set("rating", filters.rating);
  return query.toString();
}

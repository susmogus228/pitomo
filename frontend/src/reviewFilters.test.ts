import { describe, expect, it } from "vitest";
import {
  readReviewFilters,
  reviewApiQuery,
  updateReviewFilters,
} from "./reviewFilters";

describe("review filters", () => {
  it("bounds external query values and rejects unsupported sort/rating", () => {
    expect(
      readReviewFilters(
        new URLSearchParams("reviews_page=-2&review_sort=fake&review_rating=9"),
      ),
    ).toEqual({ page: 1, sort: "newest", rating: "", withPhotos: false });
  });
  it("preserves the chosen variant and resets pagination when filtering", () => {
    const params = updateReviewFilters(
      new URLSearchParams("variant=21&reviews_page=3"),
      { rating: "4", withPhotos: true },
    );
    expect(params.get("variant")).toBe("21");
    expect(params.has("reviews_page")).toBe(false);
    expect(reviewApiQuery(readReviewFilters(params))).toBe(
      "limit=5&offset=0&sort=newest&with_photos=true&rating=4",
    );
  });
  it("sort and photos are independent from rating and retained between pages", () => {
    const params = updateReviewFilters(
      new URLSearchParams(
        "review_sort=rating_asc&review_photos=true&review_rating=2",
      ),
      { page: 2 },
    );
    expect(readReviewFilters(params)).toEqual({
      page: 2,
      sort: "rating_asc",
      rating: "2",
      withPhotos: true,
    });
    expect(reviewApiQuery(readReviewFilters(params))).toContain("offset=5");
  });
});

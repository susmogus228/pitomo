import { describe, expect, it } from "vitest";
import {
  MAX_PRODUCT_PHOTO_BYTES,
  movePhotoToCover,
  productGalleryUrls,
  validateProductPhotoFiles,
} from "./ProductPhotos";
import type { Product } from "./types";

const file = { name: "cat.png", type: "image/png", size: 100 };
const product: Product = {
  id: 1,
  name: "Корм",
  pet_type: "cat",
  brand: "Питомо",
  category: "food",
  description: "Корм",
  variants: [],
};

describe("product photo selection", () => {
  it("checks the total including saved photos and refuses unsupported or oversized files", () => {
    expect(validateProductPhotoFiles([file], 4)).toBe("");
    expect(validateProductPhotoFiles([file, file], 4)).toContain("пяти");
    expect(
      validateProductPhotoFiles([{ ...file, type: "image/svg+xml" }]),
    ).toContain("JPEG");
    expect(validateProductPhotoFiles([{ ...file, size: 0 }])).toContain(
      "пустой",
    );
    expect(
      validateProductPhotoFiles([{ ...file, size: MAX_PRODUCT_PHOTO_BYTES }]),
    ).toBe("");
    expect(
      validateProductPhotoFiles([
        { ...file, size: MAX_PRODUCT_PHOTO_BYTES + 1 },
      ]),
    ).toContain("5 МБ");
  });
  it("keeps all photos when changing cover without mutating the original selection", () => {
    const photos = ["first", "second", "third"];
    expect(movePhotoToCover(photos, 2)).toEqual(["third", "first", "second"]);
    expect(photos).toEqual(["first", "second", "third"]);
    expect(movePhotoToCover(photos, 8)).toEqual(photos);
  });
  it("preserves a legacy cover and removes duplicate thumbnails", () => {
    expect(
      productGalleryUrls({
        ...product,
        image_url: "/media/old.png",
        images: [
          { id: 2, url: "/media/products/2.webp" },
          { id: 3, url: "/media/old.png" },
        ],
      }),
    ).toEqual(["/media/old.png", "/media/products/2.webp"]);
    expect(
      productGalleryUrls({
        ...product,
        images: [{ id: 2, url: "/media/products/2.webp" }],
      }),
    ).toEqual(["/media/products/2.webp"]);
    expect(productGalleryUrls(product)).toEqual(["/media/products/food.png"]);
  });
});

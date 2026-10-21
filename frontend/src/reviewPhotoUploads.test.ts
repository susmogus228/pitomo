import { describe, expect, it, vi } from "vitest";
import { uploadReviewPhotoFiles } from "./reviewPhotoUploads";

describe("review photo recovery", () => {
  it("keeps only failed files and continues after a failed upload", async () => {
    const first = new File(["1"], "first.png");
    const second = new File(["2"], "second.png");
    const third = new File(["3"], "third.png");
    const upload = vi.fn(async (file: File) => {
      if (file === second) throw new Error("offline");
    });
    const result = await uploadReviewPhotoFiles([first, second, third], upload);
    expect(result.uploaded).toBe(2);
    expect(result.failed).toEqual([second]);
    expect(result.errors).toEqual(["offline"]);
    const retry = vi.fn(async () => undefined);
    expect((await uploadReviewPhotoFiles(result.failed, retry)).failed).toEqual(
      [],
    );
    expect(retry).toHaveBeenCalledTimes(1);
    expect(retry).toHaveBeenCalledWith(second);
  });
  it("handles an empty selection without sending an upload", async () => {
    const upload = vi.fn();
    expect(await uploadReviewPhotoFiles([], upload)).toEqual({
      uploaded: 0,
      failed: [],
      errors: [],
    });
    expect(upload).not.toHaveBeenCalled();
  });
});

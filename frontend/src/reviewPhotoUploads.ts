export interface ReviewPhotoUploadResult {
  uploaded: number;
  failed: File[];
  errors: string[];
}

export async function uploadReviewPhotoFiles(
  files: readonly File[],
  upload: (file: File) => Promise<unknown>,
): Promise<ReviewPhotoUploadResult> {
  const result: ReviewPhotoUploadResult = {
    uploaded: 0,
    failed: [],
    errors: [],
  };
  for (const file of files) {
    try {
      await upload(file);
      result.uploaded += 1;
    } catch (problem) {
      result.failed.push(file);
      result.errors.push(
        problem instanceof Error
          ? problem.message
          : "Не удалось загрузить фото.",
      );
    }
  }
  return result;
}

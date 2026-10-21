import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api, messageOf } from "./api";
import { ErrorNotice } from "./components";
import { productImage } from "./lib";
import { mediaUrl } from "./media";
import type { Product } from "./types";
import "./product-photos.css";

export const MAX_PRODUCT_PHOTOS = 5;
export const MAX_PRODUCT_PHOTO_BYTES = 5 * 1024 * 1024;
const PHOTO_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const PHOTO_ACCEPT = "image/jpeg,image/png,image/webp";

function ProductPhoto({
  src,
  alt,
  width,
  height,
  loading,
}: {
  src: string;
  alt: string;
  width: number;
  height: number;
  loading?: "lazy";
}) {
  const [failed, setFailed] = useState<string | null>(null);
  if (failed === src)
    return (
      <span
        className="product-photo-placeholder"
        role={alt ? "img" : undefined}
        aria-label={alt ? `${alt}. Фото недоступно.` : undefined}
        aria-hidden={alt ? undefined : true}
      >
        Фото недоступно
      </span>
    );
  return (
    <img
      src={mediaUrl(src)}
      alt={alt}
      width={width}
      height={height}
      loading={loading}
      onError={() => setFailed(src)}
    />
  );
}

export function validateProductPhotoFiles(
  files: readonly Pick<File, "name" | "type" | "size">[],
  count = 0,
): string {
  if (count + files.length > MAX_PRODUCT_PHOTOS)
    return "У товара может быть не больше пяти фотографий.";
  for (const file of files) {
    if (!PHOTO_TYPES.has(file.type))
      return `«${file.name}»: выберите фотографию JPEG, PNG или WebP.`;
    if (!file.size)
      return `«${file.name}»: файл пустой. Выберите другую фотографию.`;
    if (file.size > MAX_PRODUCT_PHOTO_BYTES)
      return `«${file.name}»: размер фотографии должен быть не больше 5 МБ.`;
  }
  return "";
}

export function movePhotoToCover<T>(photos: readonly T[], index: number): T[] {
  if (index < 0 || index >= photos.length || !Number.isInteger(index))
    return [...photos];
  return [photos[index], ...photos.filter((_, position) => position !== index)];
}

export function productGalleryUrls(product: Product): string[] {
  const photos = (product.images || []).map((photo) => photo.url);
  const cover = product.image_url || photos[0] || productImage(product);
  return [...new Set([cover, ...photos])];
}

export function DraftProductPhotos({
  files,
  onChange,
  disabled,
}: {
  files: File[];
  onChange: (files: File[]) => void;
  disabled: boolean;
}) {
  const [previews, setPreviews] = useState<string[]>([]);
  const [error, setError] = useState("");
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const urls = files.map((file) => URL.createObjectURL(file));
    setPreviews(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [files]);
  return (
    <section
      className="product-photo-editor"
      aria-labelledby="draft-photos-title"
    >
      <h3 id="draft-photos-title">Фотографии товара</h3>
      <p className="form-note">
        До 5 фотографий JPEG, PNG или WebP, до 5 МБ каждая. Обложка появится в
        каталоге. Фотографии сохранятся вместе с товаром.
      </p>
      <label className="field product-photo-picker">
        <span>Выберите фотографии</span>
        <input
          type="file"
          accept={PHOTO_ACCEPT}
          multiple
          disabled={disabled || files.length >= MAX_PRODUCT_PHOTOS}
          onChange={(event) => {
            const chosen = Array.from(event.target.files || []);
            event.target.value = "";
            const problem = validateProductPhotoFiles(chosen, files.length);
            setError(problem);
            if (problem)
              window.requestAnimationFrame(() => errorRef.current?.focus());
            else onChange([...files, ...chosen]);
          }}
        />
      </label>
      <div ref={errorRef} tabIndex={-1}>
        <ErrorNotice message={error} />
      </div>
      {files.length ? (
        <ul className="product-photo-list">
          {files.map((file, index) => (
            <li
              className="product-photo-item"
              key={`${file.name}-${file.size}-${file.lastModified}-${index}`}
            >
              {previews[index] && (
                <ProductPhoto
                  src={previews[index]}
                  alt={`Предпросмотр: ${file.name}`}
                  width={160}
                  height={160}
                />
              )}
              <span className="product-photo-name" title={file.name}>
                {file.name}
              </span>
              {index === 0 && (
                <span className="product-photo-cover">Обложка</span>
              )}
              <div className="product-photo-actions">
                <button
                  type="button"
                  className="text-button"
                  disabled={disabled || index === 0}
                  aria-label={`Сделать фотографию ${index + 1} обложкой`}
                  onClick={() => onChange(movePhotoToCover(files, index))}
                >
                  На обложку
                </button>
                <button
                  type="button"
                  className="text-button"
                  disabled={disabled}
                  aria-label={`Убрать фотографию ${index + 1}`}
                  onClick={() => {
                    setError("");
                    onChange(files.filter((_, position) => position !== index));
                  }}
                >
                  Убрать
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="form-note">Фотографии пока не выбраны.</p>
      )}
    </section>
  );
}

export function SavedProductPhotos({
  product,
  onSaved,
  onBusyChange,
  disabled,
}: {
  product: Product;
  onSaved: (product: Product) => void;
  onBusyChange: (busy: boolean) => void;
  disabled: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const saving = useRef(false);
  const errorRef = useRef<HTMLDivElement>(null);
  const photos = product.images || [];
  const action = async (task: () => Promise<Product>, note: string) => {
    if (saving.current || disabled) return;
    saving.current = true;
    setBusy(true);
    onBusyChange(true);
    setError("");
    setSuccess("");
    try {
      onSaved(await task());
      setSuccess(note);
    } catch (problem) {
      setError(messageOf(problem));
      window.requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      saving.current = false;
      setBusy(false);
      onBusyChange(false);
    }
  };
  const locked = busy || disabled;
  return (
    <section
      className="product-photo-editor"
      aria-labelledby="saved-photos-title"
      aria-busy={busy}
    >
      <h3 id="saved-photos-title">Фотографии товара</h3>
      <p className="form-note">
        До 5 фотографий JPEG, PNG или WebP, до 5 МБ каждая. Изменения фотографий
        сохраняются сразу.
      </p>
      <label className="field product-photo-picker">
        <span>Добавить фотографию</span>
        <input
          type="file"
          accept={PHOTO_ACCEPT}
          disabled={locked || photos.length >= MAX_PRODUCT_PHOTOS}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (!file) return;
            const problem = validateProductPhotoFiles([file], photos.length);
            if (problem) {
              setError(problem);
              window.requestAnimationFrame(() => errorRef.current?.focus());
              return;
            }
            const body = new FormData();
            body.append("file", file);
            void action(
              () =>
                api<Product>(`/products/${product.id}/photos`, {
                  method: "POST",
                  body,
                }),
              "Фотография добавлена.",
            );
          }}
        />
      </label>
      {busy && (
        <p className="form-note" role="status">
          Сохраняем фотографии…
        </p>
      )}
      <div ref={errorRef} tabIndex={-1}>
        <ErrorNotice message={error} />
      </div>
      {success && (
        <p className="success-text" role="status">
          {success}
        </p>
      )}
      {product.image_url &&
        !photos.some((photo) => photo.url === product.image_url) && (
          <div className="product-photo-existing">
            <ProductPhoto
              src={product.image_url}
              alt="Текущая обложка товара"
              width={100}
              height={100}
            />
            <p className="form-note">
              Текущая обложка. Выберите загруженную фотографию, чтобы заменить
              её.
            </p>
          </div>
        )}
      {photos.length ? (
        <ul className="product-photo-list">
          {photos.map((photo, index) => (
            <li className="product-photo-item" key={photo.id}>
              <ProductPhoto
                src={photo.url}
                alt={`${product.name}, фотография ${index + 1}`}
                width={160}
                height={160}
              />
              {photo.url === product.image_url && (
                <span className="product-photo-cover">Обложка</span>
              )}
              <div className="product-photo-actions">
                <button
                  type="button"
                  className="text-button"
                  disabled={locked || photo.url === product.image_url}
                  aria-label={`Сделать фотографию ${index + 1} обложкой`}
                  onClick={() =>
                    void action(
                      () =>
                        api<Product>(
                          `/products/${product.id}/photos/${photo.id}/cover`,
                          { method: "PATCH" },
                        ),
                      "Обложка обновлена.",
                    )
                  }
                >
                  На обложку
                </button>
                <button
                  type="button"
                  className="text-button"
                  disabled={locked}
                  aria-label={`Удалить фотографию ${index + 1}`}
                  onClick={() =>
                    void action(
                      () =>
                        api<Product>(
                          `/products/${product.id}/photos/${photo.id}`,
                          { method: "DELETE" },
                        ),
                      "Фотография удалена.",
                    )
                  }
                >
                  Удалить
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="form-note">Загруженных фотографий пока нет.</p>
      )}
    </section>
  );
}

export function ProductGallery({
  product,
  children,
}: {
  product: Product;
  children: ReactNode;
}) {
  const urls = productGalleryUrls(product);
  const [selected, setSelected] = useState("");
  const current = urls.includes(selected) ? selected : urls[0];
  return (
    <div className="product-gallery">
      <div className="detail-art">
        <ProductPhoto
          src={current}
          width={650}
          height={650}
          alt={`${product.name}${urls.length > 1 ? `, фотография ${urls.indexOf(current) + 1} из ${urls.length}` : ""}`}
        />
        {children}
      </div>
      {urls.length > 1 && (
        <div
          className="product-gallery-thumbnails"
          role="group"
          aria-label="Фотографии товара"
        >
          {urls.map((url, index) => (
            <button
              type="button"
              key={url}
              className={current === url ? "is-selected" : ""}
              aria-label={`Показать фотографию ${index + 1}`}
              aria-pressed={current === url}
              onClick={() => setSelected(url)}
            >
              <ProductPhoto
                src={url}
                alt=""
                width={76}
                height={76}
                loading="lazy"
              />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

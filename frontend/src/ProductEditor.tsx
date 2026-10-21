import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, json, messageOf } from "./api";
import { PRODUCT_KINDS } from "./catalog";
import { ErrorNotice, Loading } from "./components";
import { money, PETS } from "./lib";
import {
  basePrice,
  blankVariant,
  editorKinds,
  productCreatePayload,
  productDraft,
  productUpdatePayload,
  variantCreatePayload,
  variantDraft,
  variantUpdatePayload,
} from "./productEditorPayloads";
import type { ProductDraft, VariantDraft } from "./productEditorPayloads";
import type { Product, Variant } from "./types";
import { useResource } from "./useResource";
import { DraftProductPhotos, SavedProductPhotos } from "./ProductPhotos";
import {
  editorDraftKey,
  editorDraftStorage,
  loadEditorDraft,
  removeEditorDraft,
  saveEditorDraft,
  hasMemoryOnlyEditorDrafts,
  subscribeEditorDrafts,
} from "./editorDraftStorage";
import { useStore } from "./StoreContext";

interface EditorSnapshot {
  draft: ProductDraft;
  variants: VariantDraft[];
  photoNames: string[];
}
const draftPhotos = new Map<string, File[]>();
function isVariantDraft(value: unknown): value is VariantDraft {
  return Boolean(
    value &&
    typeof value === "object" &&
    ["sku", "label", "price", "stock"].every(
      (key) => typeof (value as Record<string, unknown>)[key] === "string",
    ),
  );
}
function isEditorSnapshot(value: unknown): value is EditorSnapshot {
  if (!value || typeof value !== "object") return false;
  const item = value as EditorSnapshot;
  return Boolean(
    item.draft &&
    ["name", "brand", "attribute"].every(
      (key) =>
        typeof (item.draft as unknown as Record<string, unknown>)[key] ===
        "string",
    ) &&
    PETS.some((pet) => pet.id === item.draft.pet_type) &&
    ["food", "accessory"].includes(item.draft.category) &&
    (item.draft.product_kind === "" ||
      editorKinds(item.draft.category).includes(item.draft.product_kind)) &&
    Array.isArray(item.variants) &&
    item.variants.length > 0 &&
    item.variants.every(isVariantDraft) &&
    Array.isArray(item.photoNames) &&
    item.photoNames.length <= 5 &&
    item.photoNames.every((name) => typeof name === "string"),
  );
}

interface Props {
  productId: number | null;
  onClose: () => void;
  onSaved: (product: Product) => void;
  onReplenish: (variantId: number) => void;
  onBusyChange?: (busy: boolean) => void;
}

function VariantFields({
  value,
  onChange,
  existing = false,
}: {
  value: VariantDraft;
  onChange: (next: VariantDraft) => void;
  existing?: boolean;
}) {
  return (
    <div className="product-editor-variant-fields">
      <label className="field">
        <span>Артикул (SKU)</span>
        <input
          type="text"
          required
          maxLength={100}
          value={value.sku}
          onChange={(event) => onChange({ ...value, sku: event.target.value })}
        />
      </label>
      <label className="field">
        <span>Вариант товара</span>
        <input
          type="text"
          required
          maxLength={100}
          value={value.label}
          onChange={(event) =>
            onChange({ ...value, label: event.target.value })
          }
          placeholder="Например, 500 г или размер M"
        />
      </label>
      <label className="field">
        <span>Цена без скидки, ₸</span>
        <input
          type="text"
          inputMode="decimal"
          required
          maxLength={13}
          value={value.price}
          onChange={(event) =>
            onChange({ ...value, price: event.target.value })
          }
          placeholder="0,00"
        />
      </label>
      {!existing && (
        <label className="field">
          <span>Начальный остаток, шт.</span>
          <input
            type="number"
            min={0}
            max={2147483647}
            step={1}
            required
            value={value.stock}
            onChange={(event) =>
              onChange({ ...value, stock: event.target.value })
            }
          />
        </label>
      )}
    </div>
  );
}

function VariantEditor({
  productId,
  variant,
  onSaved,
  onReplenish,
  disabled,
  onBusyChange,
  draftKey,
}: {
  productId: number;
  variant?: Variant;
  onSaved: (product: Product) => void;
  onReplenish: (variantId: number) => void;
  disabled: boolean;
  onBusyChange: (busy: boolean) => void;
  draftKey: string;
}) {
  const [draft, setDraft] = useState<VariantDraft>(
    () =>
      loadEditorDraft(editorDraftStorage(), draftKey, isVariantDraft) ||
      (variant ? variantDraft(variant) : blankVariant()),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const saving = useRef(false);
  const errorRef = useRef<HTMLDivElement>(null);
  const baseline = variant ? variantDraft(variant) : blankVariant();
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  useEffect(() => {
    if (dirty) saveEditorDraft(editorDraftStorage(), draftKey, draft);
    else removeEditorDraft(editorDraftStorage(), draftKey);
  }, [draft, draftKey, dirty]);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving.current || disabled) return;
    saving.current = true;
    setBusy(true);
    onBusyChange(true);
    setError("");
    setSuccess("");
    try {
      const payload = variant
        ? variantUpdatePayload(draft)
        : variantCreatePayload(draft);
      await api<Variant>(
        `/products/${productId}/variants${variant ? `/${variant.id}` : ""}`,
        { method: variant ? "PATCH" : "POST", body: json(payload) },
      );
      const fresh = await api<Product>(`/products/${productId}`);
      onSaved(fresh);
      setDraft(
        variant
          ? variantDraft(
              fresh.variants.find((item) => item.id === variant.id) || variant,
            )
          : blankVariant(),
      );
      removeEditorDraft(editorDraftStorage(), draftKey);
      setSuccess(variant ? "Вариант сохранён." : "Новый вариант добавлен.");
    } catch (problem) {
      setError(messageOf(problem));
      window.requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      setBusy(false);
      saving.current = false;
      onBusyChange(false);
    }
  };
  return (
    <form
      className="product-editor-variant"
      onSubmit={(event) => void submit(event)}
    >
      <h3>{variant ? variant.label : "Добавить вариант"}</h3>
      {variant && (
        <p className="form-note">
          Остаток: {variant.stock} шт.
          {variant.original_price != null && (
            <>
              {" "}
              · Цена со скидкой сейчас: {money(variant.price)}. Базовая цена:{" "}
              {money(basePrice(variant))}.
            </>
          )}
        </p>
      )}
      <fieldset disabled={busy || disabled}>
        <VariantFields
          value={draft}
          onChange={setDraft}
          existing={Boolean(variant)}
        />
      </fieldset>
      <div ref={errorRef} tabIndex={-1}>
        <ErrorNotice message={error} />
      </div>
      {success && (
        <p className="success-text" role="status">
          {success}
        </p>
      )}
      <div className="button-row">
        {dirty && (
          <button
            type="button"
            className="text-button"
            disabled={busy || disabled}
            onClick={() => {
              setDraft(baseline);
              removeEditorDraft(editorDraftStorage(), draftKey);
            }}
          >
            Сбросить изменения варианта
          </button>
        )}
        <button className="button outline" disabled={busy || disabled}>
          {busy
            ? "Сохраняем…"
            : variant
              ? "Сохранить вариант"
              : "Добавить вариант"}
        </button>
        {variant && (
          <button
            type="button"
            className="text-button"
            disabled={busy || disabled}
            onClick={() => onReplenish(variant.id)}
          >
            Пополнить остаток
          </button>
        )}
      </div>
    </form>
  );
}

function EditorContent({
  initial,
  onClose,
  onSaved,
  onReplenish,
  onBusyChange,
}: Omit<Props, "productId"> & { initial?: Product }) {
  const { user } = useStore();
  const initialDraftKey = editorDraftKey(user?.id || 0, initial?.id || null);
  const [restored] = useState(() =>
    loadEditorDraft(editorDraftStorage(), initialDraftKey, isEditorSnapshot),
  );
  const [restoredNotice, setRestoredNotice] = useState(Boolean(restored));
  const [product, setProduct] = useState(initial);
  const draftKey = editorDraftKey(user?.id || 0, product?.id || null);
  const [draft, setDraft] = useState<ProductDraft>(
    () => restored?.draft || productDraft(initial),
  );
  const [variants, setVariants] = useState<VariantDraft[]>(
    restored?.variants || [blankVariant()],
  );
  const [busy, setBusy] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [variantBusy, setVariantBusy] = useState(false);
  const [photos, setPhotos] = useState<File[]>(() =>
    restored ? draftPhotos.get(initialDraftKey) || [] : [],
  );
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [selectedVariant, setSelectedVariant] = useState<number | "new">(
    initial?.variants[0]?.id || "new",
  );
  const saving = useRef(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const dirty =
    JSON.stringify(draft) !== JSON.stringify(productDraft(product)) ||
    (!product &&
      (photos.length > 0 ||
        JSON.stringify(variants) !== JSON.stringify([blankVariant()])));
  const [memoryOnlyDraft, setMemoryOnlyDraft] = useState(() =>
    hasMemoryOnlyEditorDrafts(editorDraftStorage(), draftKey),
  );
  useEffect(() => {
    const refresh = () =>
      setMemoryOnlyDraft(
        hasMemoryOnlyEditorDrafts(editorDraftStorage(), draftKey),
      );
    refresh();
    return subscribeEditorDrafts(refresh);
  }, [draftKey]);
  useEffect(() => {
    if (dirty) {
      saveEditorDraft(editorDraftStorage(), draftKey, {
        draft,
        variants,
        photoNames: photos.map((file) => file.name),
      });
      draftPhotos.set(draftKey, photos);
    } else {
      removeEditorDraft(editorDraftStorage(), draftKey);
      draftPhotos.delete(draftKey);
    }
  }, [draftKey, draft, variants, photos, dirty]);
  useEffect(() => {
    if (!photos.length && !memoryOnlyDraft) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [photos.length, memoryOnlyDraft]);
  useEffect(() => {
    nameRef.current?.focus();
  }, []);
  const editorBusy = busy || photoBusy || variantBusy;
  useEffect(() => {
    onBusyChange?.(editorBusy);
  }, [editorBusy, onBusyChange]);
  useEffect(
    () => () => {
      onBusyChange?.(false);
    },
    [onBusyChange],
  );
  const savedVariant = (fresh: Product) => {
    setProduct(fresh);
    onSaved(fresh);
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving.current || photoBusy || variantBusy) return;
    saving.current = true;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const payload = product
        ? productUpdatePayload(draft)
        : productCreatePayload(draft, variants);
      let body: string | FormData = json(payload);
      if (!product && photos.length) {
        body = new FormData();
        body.append("data", json(payload));
        photos.forEach((file) => (body as FormData).append("files", file));
      }
      const response = await api<Product>(
        product
          ? `/products/${product.id}`
          : photos.length
            ? "/products/with-photos"
            : "/products",
        { method: product ? "PATCH" : "POST", body },
      );
      const fresh = response;
      setProduct(fresh);
      setDraft(productDraft(fresh));
      setPhotos([]);
      removeEditorDraft(editorDraftStorage(), draftKey);
      draftPhotos.delete(draftKey);
      setRestoredNotice(false);
      if (!product) setSelectedVariant(fresh.variants[0]?.id || "new");
      setSuccess(
        product
          ? "Данные товара сохранены."
          : "Товар создан и доступен в каталоге.",
      );
      onSaved(fresh);
    } catch (problem) {
      setError(messageOf(problem));
      window.requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      setBusy(false);
      saving.current = false;
    }
  };
  const variant = product?.variants.find((item) => item.id === selectedVariant);
  return (
    <section className="product-editor" aria-labelledby="product-editor-title">
      <div className="product-editor-heading">
        <h2 id="product-editor-title">
          {product ? `Редактировать товар №${product.id}` : "Новый товар"}
        </h2>
        <button
          type="button"
          className="text-button"
          disabled={editorBusy}
          onClick={onClose}
        >
          Закрыть редактор
        </button>
      </div>
      <p className="form-note">
        Несохранённые поля и варианты восстанавливаются в этой вкладке в течение
        24 часов. Выбранные фото нового товара сохраняются только до обновления
        страницы. Фотографии существующего товара сохраняются сразу.
      </p>
      {memoryOnlyDraft && (
        <p className="error-text" role="alert">
          Хранилище браузера недоступно или заполнено. Черновик сохранён только
          в памяти вкладки: можно закрывать и открывать редактор, но перед
          обновлением или закрытием вкладки сохраните товар и изменённые
          варианты.
        </p>
      )}
      {restoredNotice && (
        <p className="success-text" role="status">
          Черновик восстановлен.
          {Boolean(restored?.photoNames.length && !photos.length) &&
            " Фотографии нужно выбрать повторно после обновления страницы."}
        </p>
      )}
      {dirty && (
        <button
          type="button"
          className="text-button"
          disabled={editorBusy}
          onClick={() => {
            setDraft(productDraft(product));
            setVariants([blankVariant()]);
            setPhotos([]);
            setRestoredNotice(false);
            removeEditorDraft(editorDraftStorage(), draftKey);
            draftPhotos.delete(draftKey);
          }}
        >
          Сбросить черновик данных товара
        </button>
      )}
      <form onSubmit={(event) => void submit(event)}>
        <fieldset disabled={editorBusy}>
          <label className="field">
            <span>Название товара</span>
            <input
              type="text"
              ref={nameRef}
              required
              maxLength={200}
              value={draft.name}
              onChange={(event) =>
                setDraft({ ...draft, name: event.target.value })
              }
            />
          </label>
          <div className="product-editor-fields">
            <label className="field">
              <span>Для кого</span>
              <select
                value={draft.pet_type}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    pet_type: event.target.value as ProductDraft["pet_type"],
                  })
                }
              >
                {PETS.map((pet) => (
                  <option key={pet.id} value={pet.id}>
                    {pet.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Бренд</span>
              <input
                type="text"
                required
                maxLength={100}
                value={draft.brand}
                onChange={(event) =>
                  setDraft({ ...draft, brand: event.target.value })
                }
              />
            </label>
            <label className="field">
              <span>Категория{product ? " · задана при создании" : ""}</span>
              <select
                value={draft.category}
                disabled={Boolean(product)}
                onChange={(event) => {
                  const category = event.target
                    .value as ProductDraft["category"];
                  setDraft({
                    ...draft,
                    category,
                    product_kind: category === "food" ? "food" : "bowls",
                    attribute: "",
                  });
                }}
              >
                <option value="food">Корм и лакомства</option>
                <option value="accessory">Аксессуары и уход</option>
              </select>
            </label>
            <label className="field">
              <span>Раздел каталога</span>
              <select
                value={draft.product_kind}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    product_kind: event.target
                      .value as ProductDraft["product_kind"],
                  })
                }
              >
                <option value="" disabled={Boolean(product?.product_kind)}>
                  Не указан
                </option>
                {editorKinds(draft.category).map((kind) => (
                  <option value={kind} key={kind}>
                    {PRODUCT_KINDS[kind]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="field">
            <span>{draft.category === "food" ? "Состав" : "Материал"}</span>
            <textarea
              required
              rows={3}
              maxLength={draft.category === "food" ? 1000 : 500}
              value={draft.attribute}
              onChange={(event) =>
                setDraft({ ...draft, attribute: event.target.value })
              }
            />
          </label>
          {!product && (
            <DraftProductPhotos
              files={photos}
              onChange={setPhotos}
              disabled={editorBusy}
            />
          )}
          {!product && (
            <section
              className="product-editor-initial-variants"
              aria-labelledby="initial-variants-title"
            >
              <h3 id="initial-variants-title">Варианты нового товара</h3>
              <p className="form-note">
                Добавьте упаковку, размер или другой вариант. У каждого варианта
                должен быть свой артикул.
              </p>
              {variants.map((item, index) => (
                <div className="product-editor-draft-variant" key={index}>
                  <div className="product-editor-variant-heading">
                    <strong>Вариант {index + 1}</strong>
                    {variants.length > 1 && (
                      <button
                        type="button"
                        className="text-button"
                        onClick={() =>
                          setVariants((old) =>
                            old.filter((_, position) => position !== index),
                          )
                        }
                      >
                        Убрать из формы
                      </button>
                    )}
                  </div>
                  <VariantFields
                    value={item}
                    onChange={(next) =>
                      setVariants((old) =>
                        old.map((saved, position) =>
                          position === index ? next : saved,
                        ),
                      )
                    }
                  />
                </div>
              ))}
              <button
                type="button"
                className="button outline"
                onClick={() => setVariants((old) => [...old, blankVariant()])}
              >
                Ещё один вариант
              </button>
            </section>
          )}
        </fieldset>
        <div ref={errorRef} tabIndex={-1}>
          <ErrorNotice message={error} />
        </div>
        {success && (
          <p className="success-text" role="status">
            {success}
          </p>
        )}
        <button className="button" disabled={editorBusy}>
          {busy
            ? "Сохраняем…"
            : product
              ? "Сохранить данные товара"
              : "Создать товар"}
        </button>
      </form>
      {product && (
        <SavedProductPhotos
          product={product}
          onSaved={savedVariant}
          onBusyChange={setPhotoBusy}
          disabled={busy || variantBusy}
        />
      )}
      {product && (
        <section
          className="product-editor-variants"
          aria-labelledby="product-variants-title"
        >
          <h3 id="product-variants-title">Варианты и цены</h3>
          <label className="field">
            <span>Выберите вариант</span>
            <select
              value={selectedVariant}
              disabled={editorBusy}
              onChange={(event) =>
                setSelectedVariant(
                  event.target.value === "new"
                    ? "new"
                    : Number(event.target.value),
                )
              }
            >
              {product.variants.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label} · {item.sku} · {item.stock} шт.
                </option>
              ))}
              <option value="new">+ Новый вариант</option>
            </select>
          </label>
          <VariantEditor
            key={selectedVariant}
            productId={product.id}
            variant={variant}
            onSaved={savedVariant}
            onReplenish={onReplenish}
            disabled={busy || photoBusy}
            onBusyChange={setVariantBusy}
            draftKey={`${editorDraftKey(user?.id || 0, product.id)}:variant:${selectedVariant}`}
          />
        </section>
      )}
    </section>
  );
}

export function ProductEditor({ productId, ...props }: Props) {
  const source = useResource<Product>(
    productId ? `/products/${productId}` : null,
  );
  if (productId && source.loading)
    return <Loading text="Загружаем товар для редактирования…" />;
  if (productId && source.error)
    return <ErrorNotice message={source.error} retry={source.reload} />;
  if (productId && !source.data) return null;
  return (
    <EditorContent
      key={productId || "new"}
      initial={source.data || undefined}
      {...props}
    />
  );
}

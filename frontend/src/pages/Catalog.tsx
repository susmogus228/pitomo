import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useLocation, useSearchParams } from "react-router";
import {
  Breadcrumbs,
  Empty,
  ErrorNotice,
  FavoriteButton,
  Icon,
  Loading,
  PriceLabel,
  ProductBadges,
  ProductImage,
} from "../components";
import { itemCount, money, PETS, productImage } from "../lib";
import {
  catalogVariant,
  petSwitchParams,
  priceRange,
  PRODUCT_KINDS,
  updateCatalogParams,
} from "../catalog";
import { useResource } from "../useResource";
import { useStore } from "../StoreContext";
import { api, messageOf } from "../api";
import type {
  Product,
  ProductKind,
  ProductKindCount,
  ProductPage,
} from "../types";
import "../catalog.css";
import { mediaUrl } from "../media";

function CatalogCard({
  product,
  params,
}: {
  product: Product;
  params: URLSearchParams;
}) {
  const variant = catalogVariant(product, params);
  const { addToCart, cart } = useStore();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const quantity =
    cart?.items.find((item) => item.variant_id === variant?.id)?.quantity || 0;
  const available = Boolean(variant && variant.stock > quantity);
  const to = `/product/${product.id}${variant ? `?variant=${variant.id}` : ""}`;
  return (
    <article className="cv-card">
      <div className="cv-art">
        <Link to={to} tabIndex={-1} aria-hidden="true">
          <ProductImage
            src={productImage(product)}
            alt=""
            width={320}
            height={320}
            loading="lazy"
          />
        </Link>
        <FavoriteButton product={product} />
        <ProductBadges product={product} variant={variant} />
      </div>
      <div className="cv-card-body">
        <p className="cv-meta">
          {PETS.find((pet) => pet.id === product.pet_type)?.forLabel} ·{" "}
          {product.brand}
        </p>
        <h2>
          <Link to={to}>{product.name}</Link>
        </h2>
        <Link className="cv-rating" to={`/product/${product.id}#reviews`} aria-label={product.rating_count ? `Оценка ${product.rating_average?.toFixed(1)} из 5, отзывов: ${product.rating_count}` : "Пока без отзывов"}>
          {product.rating_count ? <><span aria-hidden="true">★</span> <strong>{product.rating_average?.toFixed(1)}</strong><span>· {product.rating_count}</span></> : <span>Пока без отзывов</span>}
        </Link>
        <p className="cv-variant">
          {variant?.label || "Выберите вариант"}
          {product.variants.length > 1 && (
            <Link to={to}> · Ещё {product.variants.length - 1}</Link>
          )}
        </p>
        <div className="cv-card-bottom">
          <strong>{variant ? <PriceLabel variant={variant} /> : "—"}</strong>
          <button
            className="cv-add"
            disabled={busy || !available}
            aria-label={
              busy
                ? "Добавляем…"
                : available
                  ? `В корзину: ${product.name}, ${variant?.label}`
                  : quantity
                    ? "В корзине весь доступный остаток"
                    : "Нет в наличии"
            }
            title={
              available
                ? "В корзину"
                : quantity
                  ? "В корзине весь доступный остаток"
                  : "Нет в наличии"
            }
            onClick={async () => {
              if (!variant) return;
              setBusy(true);
              setError("");
              try {
                await addToCart(product, variant.id);
              } catch (e) {
                setError(messageOf(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            <Icon name={busy ? "bag" : "plus"} size={18} />
          </button>
        </div>
        {!available && !busy && (
          <p className="cv-stock">
            {quantity ? "Весь остаток в корзине" : "Нет в наличии"}
          </p>
        )}
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
      </div>
    </article>
  );
}

export function Catalog() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const locationKey = useRef(location.key);
  locationKey.current = location.key;
  const { setNotice } = useStore();
  const petRequest = useRef<AbortController | null>(null);
  const [pendingPet, setPendingPet] = useState<string | null>(null);
  const [petError, setPetError] = useState("");
  useEffect(() => {
    petRequest.current?.abort();
    petRequest.current = null;
    setPendingPet(null);
    setPetError("");
    return () => petRequest.current?.abort();
  }, [location.key]);
  const query = new URLSearchParams(params);
  query.set("page_size", "12");
  const products = useResource<ProductPage>(`/products?${query}`, { keepPreviousData: true });
  const resultParams = products.dataPath ? new URLSearchParams(products.dataPath.split("?")[1]) : params;
  const pet = params.get("pet_type") || "";
  const kinds = useResource<ProductKindCount[]>(
    `/product-kinds${pet ? `?pet_type=${encodeURIComponent(pet)}` : ""}`,
  );
  const brands = useResource<string[]>("/brands");
  const selectedKind = params.get("product_kind") || "";
  const selectedPet = PETS.find((item) => item.id === pet);
  const [mobile, setMobile] = useState(
    () => matchMedia("(max-width: 800px)").matches,
  );
  const [filtersOpen, setFiltersOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const results = useRef<HTMLElement>(null);
  const [prices, setPrices] = useState({
    min: params.get("min_price") || "",
    max: params.get("max_price") || "",
  });
  const priceError = priceRange(prices.min, prices.max).error;
  const minParam = params.get("min_price") || "",
    maxParam = params.get("max_price") || "";
  useEffect(
    () => setPrices({ min: minParam, max: maxParam }),
    [minParam, maxParam],
  );
  useEffect(() => {
    const media = matchMedia("(max-width: 800px)");
    const change = () => {
      setMobile(media.matches);
      if (!media.matches) setFiltersOpen(false);
    };
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    if (!mobile || !filtersOpen || !dialog.current) return;
    const element = dialog.current;
    const overflow = document.body.style.overflow;
    element.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      if (element.open) element.close();
      document.body.style.overflow = overflow;
    };
  }, [filtersOpen, mobile]);
  const cancelPetSwitch = () => {
    petRequest.current?.abort();
    petRequest.current = null;
    setPendingPet(null);
    setPetError("");
  };
  const update = (changes: Record<string, string>, replace = false) => {
    cancelPetSwitch();
    setParams(updateCatalogParams(params, changes), { replace });
  };
  const changePet = async (nextPet: string) => {
    cancelPetSwitch();
    if (!selectedKind) {
      update({ pet_type: nextPet });
      return;
    }
    const controller = new AbortController();
    petRequest.current = controller;
    const sourceKey = location.key;
    setPendingPet(nextPet);
    try {
      const nextKinds = await api<ProductKindCount[]>(
        `/product-kinds${nextPet ? `?pet_type=${encodeURIComponent(nextPet)}` : ""}`,
        { signal: controller.signal },
      );
      if (
        controller.signal.aborted ||
        petRequest.current !== controller ||
        locationKey.current !== sourceKey
      )
        return;
      const next = petSwitchParams(params, nextPet, nextKinds);
      setParams(next.params);
      if (next.notice) setNotice(next.notice);
    } catch (error) {
      if (
        !controller.signal.aborted &&
        petRequest.current === controller &&
        locationKey.current === sourceKey
      )
        setPetError(
          `Не удалось проверить разделы для питомца. ${messageOf(error)}`,
        );
    } finally {
      if (petRequest.current === controller) {
        petRequest.current = null;
        setPendingPet(null);
      }
    }
  };
  const changePrices = (key: "min" | "max", value: string) => {
    const next = { ...prices, [key]: value };
    setPrices(next);
  };
  useEffect(() => {
    const range = priceRange(prices.min, prices.max);
    if (range.error || (range.min === minParam && range.max === maxParam)) return;
    const timer = window.setTimeout(() => {
      cancelPetSwitch();
      setParams((current) => updateCatalogParams(current, { min_price: range.min || "", max_price: range.max || "" }), { replace: true });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [prices.min, prices.max, minParam, maxParam, setParams]);
  const reset = () => {
    cancelPetSwitch();
    setPrices({ min: "", max: "" });
    setParams({});
  };
  const count = products.data?.total;
  const page =
    products.data?.page || Math.max(1, Number(params.get("page")) || 1);
  const pages = Math.ceil((count || 0) / 12);
  const changePage = (value: number) => {
    cancelPetSwitch();
    const next = new URLSearchParams(params);
    next.set("page", String(value));
    setParams(next);
    results.current?.scrollIntoView({ block: "start", behavior: "instant" });
  };
  const filterBody = (
    <>
      <div className="cv-filter-heading">
        <h2 id="catalog-filter-title">Категории</h2>
        {mobile && (
          <button
            type="button"
            aria-label="Закрыть фильтры"
            onClick={() => setFiltersOpen(false)}
          >
            <Icon name="close" />
          </button>
        )}
      </div>
      {kinds.loading ? (
        <p className="cv-filter-status">Загружаем разделы…</p>
      ) : kinds.error ? (
        <ErrorNotice message={kinds.error} retry={kinds.reload} />
      ) : (
        <nav className="cv-kinds" aria-label="Виды товаров">
          <button
            aria-pressed={!selectedKind}
            onClick={() => update({ product_kind: "", category: "" })}
          >
            Все товары
          </button>
          {kinds.data
            ?.filter(
              (kind) => !pet || kind.count > 0 || kind.id === selectedKind,
            )
            .map((kind) => (
              <button
                key={kind.id}
                aria-pressed={selectedKind === kind.id}
                onClick={() => update({ product_kind: kind.id, category: "" })}
              >
                <span>{kind.name}</span>
                <small>{kind.count}</small>
              </button>
            ))}
        </nav>
      )}
      <fieldset className="cv-filter-block">
        <legend>Цена, ₸</legend>
        <div className="cv-price-inputs">
          <label>
            <span>от</span>
            <input
              aria-label="Цена от"
              type="number"
              min="0"
              max="9999999999.99"
              step="0.01"
              inputMode="decimal"
              placeholder="0"
              value={prices.min}
              aria-invalid={Boolean(priceError)}
              aria-describedby={priceError ? "catalog-price-error" : undefined}
              onChange={(event) => changePrices("min", event.target.value)}
            />
          </label>
          <label>
            <span>до</span>
            <input
              aria-label="Цена до"
              type="number"
              min="0"
              max="9999999999.99"
              step="0.01"
              inputMode="decimal"
              placeholder="Любая"
              value={prices.max}
              aria-invalid={Boolean(priceError)}
              aria-describedby={priceError ? "catalog-price-error" : undefined}
              onChange={(event) => changePrices("max", event.target.value)}
            />
          </label>
        </div>
        {priceError && (
          <p id="catalog-price-error" className="inline-error" role="alert">
            {priceError} Пока действует предыдущий диапазон.
          </p>
        )}
      </fieldset>
      <div className="cv-filter-block">
        <label className="field">
          <span>Бренд</span>
          <select
            value={params.get("brand") || ""}
            onChange={(event) => update({ brand: event.target.value })}
          >
            <option value="">Все бренды</option>
            {brands.data?.map((brand) => (
              <option key={brand}>{brand}</option>
            ))}
          </select>
        </label>
        {brands.error && (
          <ErrorNotice message={brands.error} retry={brands.reload} />
        )}
      </div>
      <div className="cv-filter-block">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={params.get("hits_only") === "true"}
            onChange={(event) => update({ hits_only: event.target.checked ? "true" : "" })}
          />
          Хиты продаж
        </label>
      </div>
      <div className="cv-filter-block">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={params.get("in_stock") === "true"}
            onChange={(event) =>
              update({ in_stock: event.target.checked ? "true" : "" })
            }
          />
          Только в наличии
        </label>
      </div>
      <button className="cv-reset" type="button" onClick={reset}>
        Сбросить фильтры
      </button>
      {mobile && (
        <button
          className="button full-width cv-show-results"
          onClick={() => setFiltersOpen(false)}
        >
          Показать товары <Icon name="arrow" size={18} />
        </button>
      )}
    </>
  );
  const chips: { keys: string[]; label: string }[] = [];
  if (pet) chips.push({ keys: ["pet_type"], label: selectedPet?.label || pet });
  if (selectedKind)
    chips.push({
      keys: ["product_kind"],
      label: PRODUCT_KINDS[selectedKind as ProductKind] || selectedKind,
    });
  if (params.get("category"))
    chips.push({
      keys: ["category"],
      label: params.get("category") === "food" ? "Корма" : "Аксессуары",
    });
  if (params.get("q"))
    chips.push({ keys: ["q"], label: `Поиск: ${params.get("q")}` });
  if (params.get("brand"))
    chips.push({ keys: ["brand"], label: params.get("brand")! });
  if (params.get("in_stock") === "true")
    chips.push({ keys: ["in_stock"], label: "В наличии" });
  if (params.get("hits_only") === "true")
    chips.push({ keys: ["hits_only"], label: "Хиты продаж" });
  if (minParam || maxParam)
    chips.push({
      keys: ["min_price", "max_price"],
      label: `${minParam ? `от ${money(minParam)}` : ""}${minParam && maxParam ? " " : ""}${maxParam ? `до ${money(maxParam)}` : ""}`,
    });
  return (
    <div className="catalog-v2">
      <Breadcrumbs items={[{ label: "Каталог" }]} />
      <div className="cv-heading">
        <h1>Для своих.</h1>
        <span>
          {products.loading
            ? "Собираем каталог…"
            : count === undefined
              ? "Товары для питомцев"
              : itemCount(count)}
        </span>
      </div>
      <nav className="cv-pets" aria-label="Вид питомца">
        {PETS.map((item, index) => (
          <button
            key={item.id}
            aria-pressed={pet === item.id}
            aria-busy={pendingPet === (pet === item.id ? "" : item.id)}
            disabled={
              pendingPet !== null &&
              pendingPet === (pet === item.id ? "" : item.id)
            }
            onClick={() => void changePet(pet === item.id ? "" : item.id)}
          >
            <svg
              viewBox={`${(index % 4) * 448} ${index < 4 ? 0 : 480} 448 ${index < 4 ? 480 : 416}`}
              aria-hidden="true"
            >
              <defs>
                <clipPath id={`catalog-pet-${item.id}`}>
                  <rect
                    x={(index % 4) * 448}
                    y={index < 4 ? 0 : 480}
                    width="448"
                    height={index < 4 ? 480 : 416}
                  />
                </clipPath>
              </defs>
              <image
                href={mediaUrl("/media/pets-grid-1792.webp")}
                width="1792"
                height="896"
                clipPath={`url(#catalog-pet-${item.id})`}
              />
            </svg>
            <span>
              {item.id === "small_pet" ? "Мелкие питомцы" : item.label}
            </span>
          </button>
        ))}
      </nav>
      {pendingPet !== null && (
        <p className="sr-only" role="status">
          Проверяем разделы для питомца…
        </p>
      )}
      {petError && <ErrorNotice message={petError} />}
      <div className="cv-layout">
        {!mobile && (
          <aside className="cv-filters" aria-labelledby="catalog-filter-title">
            {filterBody}
          </aside>
        )}
        <section className="cv-results" aria-label="Товары" ref={results} aria-busy={products.loading || products.refreshing}>
          <div className="cv-toolbar">
            <p aria-live="polite">
              {selectedPet?.forLabel || "Все питомцы"}
              {count !== undefined && ` · ${itemCount(count)}`}
            </p>
            <button
              ref={opener}
              className="cv-open-filters"
              aria-haspopup="dialog"
              aria-expanded={filtersOpen}
              onClick={() => setFiltersOpen(true)}
            >
              <Icon name="menu" size={18} />
              Фильтры
            </button>
            <label>
              <span className="sr-only">Сортировка</span>
              <select
                value={params.get("sort") || "id"}
                onChange={(event) => update({ sort: event.target.value })}
              >
                <option value="id">По умолчанию</option>
                <option value="price_asc">Сначала дешевле</option>
                <option value="price_desc">Сначала дороже</option>
                <option value="name">По названию</option>
              </select>
            </label>
          </div>
          {chips.length > 0 && (
            <div className="cv-chips" aria-label="Выбранные фильтры">
              {chips.map((chip) => (
                <button
                  key={chip.keys.join()}
                  onClick={() =>
                    update(
                      Object.fromEntries(chip.keys.map((key) => [key, ""])),
                    )
                  }
                  aria-label={`Снять фильтр: ${chip.label}`}
                >
                  {chip.label}
                  <Icon name="close" size={12} />
                </button>
              ))}
              {chips.length > 1 && (
                <button className="cv-clear" onClick={reset}>
                  Сбросить всё
                </button>
              )}
            </div>
          )}
          {products.refreshing && <p className="form-note" role="status">Обновляем товары… Пока показаны предыдущие результаты.</p>}
          {products.error && products.data && <ErrorNotice message={products.error} retry={products.reload} />}
          {products.loading ? (
            <Loading />
          ) : products.error && !products.data ? (
            <ErrorNotice message={products.error} retry={products.reload} />
          ) : products.data?.items.length ? (
            <div className="cv-grid">
              {products.data.items.map((product) => (
                <CatalogCard
                  key={product.id}
                  product={product}
                  params={resultParams}
                />
              ))}
            </div>
          ) : (
            <Empty
              title="Пока ничего не нашлось"
              action="Посмотреть все товары"
            >
              Попробуйте другое название или уберите часть фильтров.
            </Empty>
          )}
          {pages > 1 && (
            <nav className="pagination" aria-label="Страницы каталога">
              <button
                className="button outline"
                disabled={page <= 1 || products.loading || products.refreshing}
                onClick={() => changePage(page - 1)}
              >
                Назад
              </button>
              <span>
                {page} / {pages}
              </span>
              <button
                className="button outline"
                disabled={page >= pages || products.loading || products.refreshing}
                onClick={() => changePage(page + 1)}
              >
                Дальше
              </button>
            </nav>
          )}
        </section>
      </div>
      {mobile &&
        createPortal(
          <dialog
            ref={dialog}
            className="cv-filter-dialog"
            aria-labelledby="catalog-filter-title"
            onClose={() => {
              setFiltersOpen(false);
              opener.current?.focus();
            }}
            onCancel={() => setFiltersOpen(false)}
            onClick={(event) => {
              if (event.target !== event.currentTarget) return;
              const box = event.currentTarget.getBoundingClientRect();
              if (
                event.clientX < box.left ||
                event.clientX > box.right ||
                event.clientY < box.top ||
                event.clientY > box.bottom
              )
                setFiltersOpen(false);
            }}
          >
            {filterBody}
          </dialog>,
          document.body,
        )}
    </div>
  );
}

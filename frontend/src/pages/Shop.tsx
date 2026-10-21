import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import {
  Breadcrumbs,
  Empty,
  ErrorNotice,
  FavoriteButton,
  Icon,
  Loading,
  PageTitle,
  PriceLabel,
  ProductBadges,
  ProductGrid,
  Quantity,
} from "../components";
import { useResource } from "../useResource";
import {
  availableVariant,
  PETS,
  selectFeaturedProducts,
} from "../lib";
import type { Product, ProductPage } from "../types";
import { useStore } from "../StoreContext";
import { messageOf } from "../api";
import { ProductReviews } from "../ProductReviews";
import { ProductGallery } from "../ProductPhotos";
import { productTitle } from "../pageTitles";
import { mediaUrl, illustrationSources } from "../media";

function Hero() {
  const [play, setPlay] = useState(0);
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero-copy">
        <p className="eyebrow">Для всех, кого мы любим</p>
        <h1 id="hero-title">
          У каждого —<br />
          свой характер.
        </h1>
        <p className="hero-description">
          Корм, уход и всё для жизни
          <br className="desktop-break" /> вашего питомца.
        </p>
        <Link className="button hero-cta" to="/catalog">
          В каталог <Icon name="arrow" />
        </Link>
      </div>
      <div className="hero-scene" key={play} aria-hidden="true">
        <img
          className="hero-cat"
          src={mediaUrl("/media/hero-cat-1280.webp")}
          srcSet={illustrationSources("hero-cat")}
          sizes="(max-width: 700px) 95vw, 55vw"
          alt=""
          width={900}
          height={650}
          fetchPriority="high"
        />
        <svg className="yarn-thread" viewBox="0 0 800 130" fill="none">
          <path
            d="M125 42C200 124 315 60 470 88S715 123 728 59c8-40-48-35-40 0s49 63 95 33"
            stroke="currentColor"
            strokeWidth="4"
            strokeLinecap="round"
          />
        </svg>
        <svg className="yarn-ball" viewBox="0 0 150 150" fill="none">
          <defs>
            <clipPath id="ball-clip">
              <circle cx="75" cy="75" r="68" />
            </clipPath>
          </defs>
          <circle cx="75" cy="75" r="68" fill="currentColor" />
          <g clipPath="url(#ball-clip)" stroke="#F7F4EA" strokeWidth="1.8">
            <path d="M-10 95Q60-40 160 55M-10 108Q55-35 164 70M-10 120Q52-24 166 87M-10 136Q48-10 168 104M-10 148Q43 7 170 121M-10 160Q38 25 170 140M26-10Q-13 81 115 163M40-10Q0 75 128 163M53-10Q12 70 140 158M67-10Q25 63 151 150M83-10Q41 58 159 136M97-10Q56 53 165 122M111-10Q69 45 169 104" />
          </g>
        </svg>
      </div>
      <button
        className="replay-button"
        onClick={() => setPlay((value) => value + 1)}
        aria-label="Повторить анимацию кота"
      >
        <Icon name="play" size={18} />
      </button>
    </section>
  );
}
export function Home() {
  const hits = useResource<ProductPage>("/products?hits_only=true&page_size=4&in_stock=true");
  const branded = useResource<ProductPage>(
    `/products?page_size=100&brand=${encodeURIComponent("Питомо · Демо")}&in_stock=true`,
  );
  const featured = selectFeaturedProducts(branded.data?.items || []);
  const needsFallback = Boolean(branded.data && !featured.length);
  const fallback = useResource<ProductPage>(
    needsFallback ? "/products?page_size=4&in_stock=true" : null,
  );
  const products = needsFallback ? fallback : branded;
  const visibleProducts = needsFallback ? fallback.data?.items || [] : featured;
  const loading =
    products.loading || (needsFallback && !fallback.data && !fallback.error);
  return (
    <>
      <Hero />
      <section className="pet-section" aria-labelledby="pets-title">
        <div className="section-heading">
          <h2 id="pets-title">Для кого выбираем?</h2>
          <Link className="arrow-link" to="/catalog">
            Все питомцы <span>↗</span>
          </Link>
        </div>
        <div className="pet-grid">
          {PETS.map((pet, index) => (
            <Link
              className="pet-tile"
              key={pet.id}
              to={`/catalog?pet_type=${pet.id}`}
            >
              <svg
                className="pet-illustration"
                viewBox={`${(index % 4) * 448} ${index < 4 ? 0 : 480} 448 ${index < 4 ? 480 : 416}`}
                aria-hidden="true"
              >
                <defs>
                  <clipPath id={`pet-crop-${pet.id}`}>
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
                  clipPath={`url(#pet-crop-${pet.id})`}
                />
              </svg>
              <span>
                {pet.label}
                <Icon name="arrow" size={21} />
              </span>
            </Link>
          ))}
        </div>
      </section>
      <section className="featured-section" aria-labelledby="featured-title">
        <div className="section-heading">
          <h2 id="featured-title">Для хорошего дня</h2>
          <Link className="arrow-link" to="/catalog">
            Весь каталог <span>↗</span>
          </Link>
        </div>
        {loading ? (
          <Loading text="Собираем витрину…" />
        ) : products.error ? (
          <ErrorNotice message={products.error} retry={products.reload} />
        ) : visibleProducts.length ? (
          <ProductGrid products={visibleProducts} />
        ) : (
          <Empty title="Витрина скоро наполнится">
            Пока в магазине нет товаров.
          </Empty>
        )}
      </section>
      {hits.data?.items.length ? <section className="featured-section" aria-labelledby="hits-title">
        <div className="section-heading"><h2 id="hits-title">Хиты продаж</h2><Link className="arrow-link" to="/catalog?hits_only=true">Все хиты <span>↗</span></Link></div>
        <ProductGrid products={hits.data.items} />
      </section> : null}
    </>
  );
}

export function ProductDetail() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const resource = useResource<Product>(`/products/${id}`);
  const { addToCart, cart } = useStore();
  const [quantity, setQuantity] = useState(
    Math.min(10000, Math.max(1, Math.floor(Number(params.get("qty")) || 1))),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [added, setAdded] = useState(false);
  const product = resource.data;
  useEffect(() => { if (product) document.title = productTitle(product.name); }, [product, id]);
  const variant =
    product?.variants.find(
      (item) => item.id === Number(params.get("variant")),
    ) ||
    (product && availableVariant(product));
  const alreadyInCart =
    cart?.items.find((item) => item.variant_id === variant?.id)?.quantity || 0;
  const available = Math.max(
    0,
    Math.min(10000, (variant?.stock || 0) - alreadyInCart),
  );
  useEffect(() => {
    setAdded(false);
    setError("");
    setQuantity((value) => Math.max(1, Math.min(value, available)));
  }, [variant?.id, available]);
  if (resource.loading) return <Loading text="Загружаем товар…" />;
  if (resource.error)
    return <ErrorNotice message={resource.error} retry={resource.reload} />;
  if (!product) return <Empty title="Товар не найден" />;
  return (
    <>
      <Breadcrumbs
        items={[
          { label: "Каталог", to: "/catalog" },
          {
            label:
              PETS.find((pet) => pet.id === product.pet_type)?.label ||
              "Питомцы",
            to: `/catalog?pet_type=${product.pet_type}`,
          },
          { label: product.name },
        ]}
      />
      <article className="product-detail">
        <ProductGallery key={product.id} product={product}>
          <FavoriteButton product={product} />
          <ProductBadges product={product} variant={variant} />
        </ProductGallery>
        <div className="detail-copy">
          <p className="eyebrow">
            {product.brand} ·{" "}
            {PETS.find((pet) => pet.id === product.pet_type)?.forLabel}
          </p>
          <h1>{product.name}</h1>
          <a className="product-rating detail-rating" href="#reviews">{product.rating_count ? `★ ${product.rating_average?.toFixed(1)} / 5 · ${product.rating_count} отзывов` : "Пока без отзывов"}</a>
          <p className="detail-description">{product.description}</p>
          {variant && (
            <>
              <fieldset className="variant-options">
                <legend>Выберите вариант</legend>
                <div>
                  {product.variants.map((item) => (
                    <button
                      type="button"
                      className={variant.id === item.id ? "selected" : ""}
                      key={item.id}
                      aria-pressed={variant.id === item.id}
                      onClick={() => {
                        setParams(
                          { variant: String(item.id) },
                          { replace: true },
                        );
                        setQuantity(1);
                      }}
                    >
                      {item.label}
                      {item.stock === 0 && <small>Нет в наличии</small>}
                    </button>
                  ))}
                </div>
              </fieldset>
              <div className="detail-price">
                <strong><PriceLabel variant={variant} /></strong>
                <span className={variant.stock > 0 ? "stock-state" : "muted"}>
                  {variant.stock > 0
                    ? `В наличии: ${variant.stock} шт.`
                    : "Нет в наличии"}
                </span>
              </div>
              <div className="purchase-row">
                <Quantity
                  value={quantity}
                  onChange={setQuantity}
                  max={available}
                  disabled={busy || available === 0}
                />
                <button
                  className="button"
                  disabled={busy || available === 0}
                  onClick={async () => {
                    setBusy(true);
                    setError("");
                    try {
                      const success = await addToCart(
                        product,
                        variant.id,
                        quantity,
                      );
                      setAdded(success);
                    } catch (e) {
                      setError(messageOf(e));
                      resource.reload();
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  {busy
                    ? "Добавляем…"
                    : available === 0 && variant.stock > 0
                      ? "Всё уже в корзине"
                      : available === 0
                        ? "Нет в наличии"
                        : "В корзину"}
                  <Icon name="bag" size={20} />
                </button>
              </div>
              {alreadyInCart > 0 && (
                <p className="muted">
                  В вашей корзине: {alreadyInCart} шт.{" "}
                  <Link className="text-link" to="/cart">
                    Открыть
                  </Link>
                </p>
              )}
              {added && (
                <p role="status" className="success-text">
                  Добавлено. <Link to="/cart">Перейти в корзину →</Link>
                </p>
              )}
              <ErrorNotice message={error} />
              <p className="sku">Артикул: {variant.sku}</p>
            </>
          )}
          <div className="product-help">
            <p>Тестовая оплата или оплата при получении.</p>
            <Link className="text-link" to="/help">
              Как работает заказ ↗
            </Link>
          </div>
        </div>
      </article>
      <ProductReviews key={product.id} product={product} />
    </>
  );
}

export function Favorites() {
  const { favorites, refreshFavorites } = useStore();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    void refreshFavorites()
      .catch((e) => setError(messageOf(e)))
      .finally(() => setLoading(false));
  }, [refreshFavorites]);
  return (
    <>
      <PageTitle
        eyebrow="Самое любимое"
        subtitle="Сохраните то, к чему хочется вернуться."
      >
        Избранное
      </PageTitle>
      <ErrorNotice
        message={error}
        retry={() =>
          void refreshFavorites()
            .then(() => setError(""))
            .catch((e) => setError(messageOf(e)))
        }
      />
      {loading ? (
        <Loading text="Загружаем избранное…" />
      ) : favorites.length ? (
        <ProductGrid products={favorites} />
      ) : (
        !error && (
          <Empty title="Здесь будут ваши находки">
            Нажмите на сердечко рядом с понравившимся товаром.
          </Empty>
        )
      )}
    </>
  );
}

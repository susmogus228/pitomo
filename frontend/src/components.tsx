import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode, ImgHTMLAttributes } from "react";
import {
  Link,
  Navigate,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router";
import { useStore } from "./StoreContext";
import { adminAccess } from "./adminAccess";
import { messageOf } from "./api";
import { availableVariant, money, PETS, productImage, itemCount } from "./lib";
import type { Product, Variant } from "./types";
import { mediaUrl } from "./media";

export function ProductImage({ src, alt, className = "", ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const [failedSource, setFailedSource] = useState<string>();
  return failedSource === src || !src ? <span className={`product-image-placeholder ${className}`} role={alt ? "img" : undefined} aria-label={alt || undefined} aria-hidden={alt ? undefined : true}><Icon name="bag" size={32} /><span>Фото недоступно</span></span> : <img {...props} className={className} src={mediaUrl(src)} alt={alt} onError={() => setFailedSource(src)} />;
}

export function PriceLabel({ variant, prefix = "" }: { variant: Pick<Variant, "price" | "original_price" | "discount_percent">; prefix?: string }) {
  return <span className="price-label">
    <span>{prefix}{money(variant.price)}</span>
    {variant.original_price && Number(variant.original_price) > Number(variant.price) && <>
      <del>{money(variant.original_price)}</del>
      {variant.discount_percent && <small className="discount-tag">−{variant.discount_percent}%</small>}
    </>}
  </span>;
}

export function ProductBadges({ product, variant }: { product: Product; variant?: Variant | null }) {
  return product.is_hit || variant?.discount_percent ? <div className="product-badges">
    {product.is_hit && <span className="hit-tag">Хит</span>}
    {variant?.discount_percent && <span className="discount-tag">Скидка −{variant.discount_percent}%</span>}
  </div> : null;
}

export function Icon({
  name,
  size = 24,
}: {
  name:
    | "search"
    | "heart"
    | "user"
    | "bag"
    | "menu"
    | "arrow"
    | "close"
    | "check"
    | "play"
    | "minus"
    | "plus"
    | "trash"
    | "back";
  size?: number;
}) {
  const paths: Record<typeof name, ReactNode> = {
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 5 5" />
      </>
    ),
    heart: (
      <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z" />
    ),
    user: (
      <>
        <circle cx="12" cy="7" r="4" />
        <path d="M4 21v-2a8 8 0 0 1 16 0v2" />
      </>
    ),
    bag: (
      <>
        <path d="M5 7h14l1 14H4L5 7Z" />
        <path d="M9 9V6a3 3 0 0 1 6 0v3" />
      </>
    ),
    menu: <path d="M3 6h18M3 12h18M3 18h18" />,
    arrow: <path d="M3 12h17m-6-6 6 6-6 6" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    check: <path d="m4 12 5 5L20 6" />,
    play: <path d="m9 5 10 7-10 7V5Z" />,
    minus: <path d="M5 12h14" />,
    plus: <path d="M5 12h14M12 5v14" />,
    trash: (
      <>
        <path d="M3 6h18M6 6l1 15h10l1-15M9 6V3h6v3M10 10v7m4-7v7" />
      </>
    ),
    back: <path d="M21 12H4m6-6-6 6 6 6" />,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
export function Logo() {
  return (
    <span className="wordmark" aria-label="Питомо">
      <svg viewBox="0 0 276 56" aria-hidden="true" className="wordmark-art">
        <g
          fill="none"
          stroke="currentColor"
          strokeWidth="11"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M10 44V20Q10 10 20 10H30Q40 10 40 20V44M58 10V44L83 10V44M99 10H130M114.5 10V44M190 44V10L205 28L220 10V44" />
          <circle cx="157" cy="27" r="17" />
          <circle cx="250" cy="27" r="17" />
        </g>
        <g fill="#3457EB">
          <circle cx="157" cy="27" r="6.5" />
          <circle cx="250" cy="27" r="6.5" />
        </g>
      </svg>
    </span>
  );
}
export function Header() {
  const { user, cart, favorites, authLoading } = useStore();
  const location = useLocation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") || "");
  const [menu, setMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setMenu(false);
    setQuery(
      location.pathname === "/catalog"
        ? new URLSearchParams(location.search).get("q") || ""
        : "",
    );
  }, [location.pathname, location.search]);
  useEffect(() => {
    if (!menu) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenu(false);
        (
          document.getElementById("catalog-menu-button") as HTMLElement | null
        )?.focus();
      }
    };
    const outside = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenu(false);
    };
    document.addEventListener("keydown", close);
    document.addEventListener("click", outside);
    return () => {
      document.removeEventListener("keydown", close);
      document.removeEventListener("click", outside);
    };
  }, [menu]);
  const search = (event: FormEvent) => {
    event.preventDefault();
    navigate(
      `/catalog${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ""}`,
    );
  };
  return (
    <header className="header shell">
      <Link to="/" className="logo-link" aria-label="Питомо — на главную">
        <Logo />
      </Link>
      <div className="catalog-menu" ref={menuRef}>
        <button
          id="catalog-menu-button"
          aria-label="Каталог"
          className="button catalog-button"
          aria-expanded={menu}
          aria-controls="catalog-navigation"
          onClick={() => setMenu((value) => !value)}
        >
          <Icon name={menu ? "close" : "menu"} />
          <span>Каталог</span>
        </button>
        {menu && (
          <nav
            id="catalog-navigation"
            className="catalog-dropdown"
            aria-label="Каталог по питомцам"
          >
            <Link className="all-pets-link" to="/catalog">
              Все товары <Icon name="arrow" size={18} />
            </Link>
            {PETS.map((pet) => (
              <Link key={pet.id} to={`/catalog?pet_type=${pet.id}`}>
                {pet.label}
                <span>↗</span>
              </Link>
            ))}
            <Link to="/catalog?hits_only=true">Хиты продаж <span>↗</span></Link>
            <Link to="/vets">Ветклиники рядом <span>↗</span></Link>
          </nav>
        )}
      </div>
      <form className="header-search" role="search" onSubmit={search}>
        <label className="sr-only" htmlFor="site-search">
          Поиск товаров
        </label>
        <input
          id="site-search"
          type="search"
          maxLength={100}
          placeholder="Найти корм, товар или питомца"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button type="submit" aria-label="Найти">
          <Icon name="search" size={22} />
        </button>
      </form>
      <nav className="header-actions" aria-label="Личный кабинет">
        <Link
          to="/favorites"
          aria-label={`Избранное${favorites.length ? `, ${itemCount(favorites.length)}` : ""}`}
        >
          <Icon name="heart" />
          <span>Избранное</span>
        </Link>
        <Link to="/account" aria-label={user ? "Личный кабинет" : "Войти"}>
          <Icon name="user" />
          <span>
            {authLoading ? "Аккаунт" : user ? user.first_name : "Войти"}
          </span>
        </Link>
        <Link
          to="/cart"
          className="header-cart"
          aria-label={`Корзина, ${itemCount(cart?.total_items || 0)}`}
        >
          <Icon name="bag" />
          <span>Корзина</span>
          <b>{cart?.total_items || 0}</b>
        </Link>
      </nav>
    </header>
  );
}
export function Footer() {
  return (
    <footer className="footer shell">
      <Link to="/" aria-label="Питомо — на главную">
        <Logo />
      </Link>
      <p>Для всех, кого мы любим.</p>
      <nav aria-label="О магазине">
        <Link to="/about">О магазине</Link>
        <Link to="/help">Доставка и оплата</Link>
        <Link to="/help#contacts">Помощь</Link>
        <Link to="/vets">Ветклиники рядом</Link>
        <Link to="/privacy">Персональные данные</Link>
        <Link to="/consent">Согласия</Link>
      </nav>
      <small>Демонстрационный магазин · Деньги не списываются</small>
    </footer>
  );
}
export function PageTitle({
  eyebrow,
  children,
  subtitle,
}: {
  eyebrow?: string;
  children: ReactNode;
  subtitle?: string;
}) {
  return (
    <div className="page-title">
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      <h1>{children}</h1>
      {subtitle && <p>{subtitle}</p>}
    </div>
  );
}
export function ErrorNotice({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  if (!message) return null;
  return (
    <div className="error-notice" role="alert">
      <p>{message}</p>
      {retry && (
        <button className="text-button" onClick={retry}>
          Попробовать снова
        </button>
      )}
    </div>
  );
}
export function Loading({ text = "Загружаем…" }: { text?: string }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" />
      {text}
    </div>
  );
}
export function Empty({
  title,
  children,
  action = "В каталог",
  to = "/catalog",
}: {
  title: string;
  children?: ReactNode;
  action?: string;
  to?: string;
}) {
  return (
    <div className="empty-state">
      <span className="empty-ball" aria-hidden="true">
        ◎
      </span>
      <h2>{title}</h2>
      {children && <p>{children}</p>}
      <Link className="button" to={to}>
        {action}
        <Icon name="arrow" size={18} />
      </Link>
    </div>
  );
}
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, authLoading, sessionError, refreshSession } = useStore();
  const location = useLocation();
  if (authLoading) return <Loading text="Проверяем вход…" />;
  if (sessionError)
    return (
      <ErrorNotice message={sessionError} retry={() => void refreshSession()} />
    );
  if (!user)
    return (
      <Navigate
        to={`/login?returnTo=${encodeURIComponent(location.pathname + location.search)}`}
        replace
      />
    );
  return children;
}
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { user, authLoading, sessionError, refreshSession } = useStore();
  const location = useLocation();
  const access = adminAccess(user, authLoading, sessionError);
  if (access === "loading") return <Loading text="Проверяем права доступа…" />;
  if (access === "error") return <ErrorNotice message={sessionError} retry={() => void refreshSession()} />;
  if (access === "login") return <Navigate to={`/login?returnTo=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  if (access === "denied") return <div className="empty-state" role="alert"><h1>Нет доступа</h1><p>Эта страница доступна только администраторам магазина.</p><Link className="button" to="/">На главную</Link></div>;
  return children;
}
export function Quantity({
  value,
  onChange,
  max,
  disabled = false,
  label = "Количество",
}: {
  value: number;
  onChange: (quantity: number) => void;
  max: number;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <div className="quantity" role="group" aria-label={label}>
      <button
        type="button"
        aria-label={`Уменьшить: ${label}`}
        disabled={disabled || value <= 1}
        onClick={() => onChange(value - 1)}
      >
        <Icon name="minus" size={16} />
      </button>
      <output aria-live="polite">{value}</output>
      <button
        type="button"
        aria-label={`Увеличить: ${label}`}
        disabled={disabled || value >= max}
        onClick={() => onChange(value + 1)}
      >
        <Icon name="plus" size={16} />
      </button>
    </div>
  );
}
export function FavoriteButton({ product }: { product: Product }) {
  const { favorites, toggleFavorite } = useStore();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const selected = favorites.some((item) => item.id === product.id);
  return (
    <>
      <button
        className={`favorite-button ${selected ? "selected" : ""}`}
        aria-label={`${selected ? "Убрать из избранного" : "В избранное"}: ${product.name}`}
        aria-pressed={selected}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            await toggleFavorite(product);
          } catch (e) {
            setError(messageOf(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        <Icon name="heart" size={22} />
      </button>
      {error && (
        <span className="card-error" role="alert">
          {error}
        </span>
      )}
    </>
  );
}
export function ProductCard({ product }: { product: Product }) {
  const variant = availableVariant(product);
  const { addToCart } = useStore();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const available = product.variants.some((item) => item.stock > 0);
  return (
    <article className="product-card">
      <div className="product-art">
        <Link to={`/product/${product.id}`} tabIndex={-1} aria-hidden="true">
          <ProductImage
            src={productImage(product)}
            alt=""
            width={360}
            height={360}
            loading="lazy"
          />
        </Link>
        <FavoriteButton product={product} />
        <ProductBadges product={product} variant={variant} />
      </div>
      <div className="product-card-body">
        <p className="product-meta">
          {PETS.find((pet) => pet.id === product.pet_type)?.forLabel} ·{" "}
          {product.brand}
        </p>
        <h3>
          <Link to={`/product/${product.id}`}>{product.name}</Link>
        </h3>
        <Link className="product-rating" to={`/product/${product.id}#reviews`} aria-label={product.rating_count ? `Оценка ${product.rating_average?.toFixed(1)} из 5, отзывов: ${product.rating_count}` : "Пока без отзывов"}>
          {product.rating_count ? `★ ${product.rating_average?.toFixed(1)} · ${product.rating_count} отзывов` : "Пока без отзывов"}
        </Link>
        <p className="variant-label">
          {product.variants.length > 1
            ? `${product.variants.length} варианта`
            : variant?.label || "Нет вариантов"}
        </p>
        <p className="price">
          {variant
            ? <PriceLabel variant={variant} prefix={product.variants.length > 1 ? "от " : ""} />
            : "Нет в продаже"}
        </p>
        {product.variants.length > 1 ? (
          <Link
            className="button outline"
            to={`/product/${product.id}${variant ? `?variant=${variant.id}` : ""}`}
          >
            Выбрать
          </Link>
        ) : (
          <button
            className="button outline"
            disabled={busy || !available || !variant}
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
            {busy ? "Добавляем…" : available ? "В корзину" : "Нет в наличии"}
          </button>
        )}
        {error && (
          <p role="alert" className="inline-error">
            {error}
          </p>
        )}
      </div>
    </article>
  );
}
export function ProductGrid({ products }: { products: Product[] }) {
  return (
    <div className="product-grid">
      {products.map((product) => (
        <ProductCard key={product.id} product={product} />
      ))}
    </div>
  );
}
export function Breadcrumbs({
  items,
}: {
  items: { label: string; to?: string }[];
}) {
  return (
    <nav className="breadcrumbs" aria-label="Хлебные крошки">
      <Link to="/">Главная</Link>
      {items.map((item, index) => (
        <span key={`${item.label}-${index}`}>
          <span aria-hidden="true">/</span>
          {item.to ? (
            <Link to={item.to}>{item.label}</Link>
          ) : (
            <span aria-current="page">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, NavLink, Outlet, useLocation, useSearchParams } from "react-router";
import { api, json, messageOf } from "../api";
import { ErrorNotice, Loading, PageTitle } from "../components";
import { useResource } from "../useResource";
import type { Product, ProductPage, User } from "../types";
import { ExportControls } from "../ExportControls";
import { ProductEditor } from "../ProductEditor";
import { money, PETS } from "../lib";
import { PRODUCT_KINDS } from "../catalog";
import "../admin.css";
import { adminPage, ORDER_QUEUES } from "../adminFilters";
import { useStore } from "../StoreContext";
import { AdminReviewModeration } from "../AdminReviewModeration";

const sections = [
  { to: "/admin", label: "Обзор", end: true },
  { to: "/admin/products", label: "Товары и остатки" },
  { to: "/admin/orders", label: "Заказы" },
  { to: "/admin/reviews", label: "Отзывы" },
  { to: "/admin/discounts", label: "Скидки" },
  { to: "/admin/users", label: "Пользователи" },
];

export function AdminLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  const currentSection = [...sections].reverse().find((section) => section.end ? pathname === section.to : pathname.startsWith(section.to))?.label || "Обзор";
  return <div className="admin-shell">
    <div className="admin-topline"><div><span className="eyebrow">Питомо · управление магазином</span><p className="admin-brand">Панель администратора</p></div>
      <button type="button" className="button outline admin-menu-toggle" aria-expanded={menuOpen} aria-controls="admin-navigation" onClick={() => setMenuOpen((value) => !value)}>{menuOpen ? "Закрыть меню" : `Раздел: ${currentSection}`}</button>
    </div>
    <div className="admin-layout">
      <nav id="admin-navigation" className={`admin-nav ${menuOpen ? "is-open" : ""}`} aria-label="Разделы админ-панели">
        {sections.map((section) => <NavLink key={section.to} to={section.to} end={section.end} onClick={() => setMenuOpen(false)} className={({ isActive }) => isActive ? "active" : ""}>{section.label}</NavLink>)}
        <Link className="admin-exit" to="/account">Вернуться в личный кабинет ↗</Link>
      </nav>
      <div className="admin-content"><Outlet /></div>
    </div>
  </div>;
}

interface Dashboard {
  orders_total: number;
  orders_pending: number;
  products_total: number;
  low_stock_variants: number;
  low_stock_products: number;
  order_queues: Record<string, number>;
  reviews_total: number;
  unanswered_reviews: number;
}
export function AdminOverview() {
  const { user } = useStore();
  const stats = useResource<Dashboard>("/admin/dashboard", { scope: user?.id });
  return <section>
    <PageTitle eyebrow="Состояние магазина" subtitle="Показатели отражают текущие данные магазина.">Обзор</PageTitle>
    {stats.loading ? <Loading text="Загружаем показатели…" /> : stats.error ? <ErrorNotice message={stats.error} retry={stats.reload} /> : stats.data ? <>
      <div className="admin-stats">
        <Link to="/admin/orders"><span>Всего заказов</span><strong>{stats.data.orders_total}</strong></Link>
        <Link to="/admin/orders?queue=active"><span>Ожидают завершения</span><strong>{stats.data.orders_pending}</strong></Link>
        <Link to="/admin/products"><span>Товаров</span><strong>{stats.data.products_total}</strong></Link>
        <Link to="/admin/products?stock_max=5"><span>Товаров с малым остатком</span><strong>{stats.data.low_stock_products}</strong><small>{stats.data.low_stock_variants} вариантов · порог 5 шт.</small></Link>
        <Link to="/admin/reviews"><span>Отзывов</span><strong>{stats.data.reviews_total}</strong></Link>
        <Link to="/admin/reviews?unanswered=true"><span>Без ответа магазина</span><strong>{stats.data.unanswered_reviews}</strong></Link>
      </div>
      <nav className="admin-queues" aria-label="Рабочие очереди заказов">{ORDER_QUEUES.filter(([id]) => id !== "active").map(([id, label]) => <Link key={id} to={`/admin/orders?queue=${id}`}><span>{label}</span><strong>{stats.data!.order_queues?.[id] || 0}</strong></Link>)}</nav>
      <div className="admin-next"><h2>Что проверить</h2><p>Заказы покупателей, остатки и отзывы собраны в отдельных разделах. Для пополнения выберите товар и его вариант.</p><div className="button-row"><Link className="button" to="/admin/products">Открыть остатки</Link><Link className="button outline" to="/admin/reviews?unanswered=true">Отзывы без ответа</Link></div></div>
    </> : null}
    <ExportControls dataset="overview" title="Сводка за период" />
    <ExportControls dataset="all" title="Все данные для аналитики" />
  </section>;
}

interface Replenishment {
  id: number;
  variant_id: number;
  product_name: string;
  variant_label: string;
  sku: string;
  quantity: number;
  stock_before: number;
  stock_after: number;
  reason: string;
  created_at: string;
  actor_id: number;
}
interface ReplenishmentPage { items: Replenishment[]; total: number; limit: number; offset: number }
const dateTime = (value: string) => new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));

export function AdminProducts() {
  const { user } = useStore();
  const [searchParams, setSearchParams] = useSearchParams();
  const [editingId, setEditingId] = useState<number | null | undefined>(undefined);
  const [editorRevision, setEditorRevision] = useState(0);
  const [editorBusy, setEditorBusy] = useState(false);
  const [editorProduct, setEditorProduct] = useState<Product | null>(null);
  const [focusStock, setFocusStock] = useState(false);
  const query = searchParams.get("q") || "";
  const [search, setSearch] = useState(query);
  const page = adminPage(searchParams);
  const rawStock = Number(searchParams.get("stock_max"));
  const stockMax = searchParams.has("stock_max") && Number.isInteger(rawStock) && rawStock >= 0 && rawStock <= 2147483647 ? rawStock : undefined;
  const updateQuery = (changes: Record<string, string | undefined>, resetPage = true) => setSearchParams((current) => { const next = new URLSearchParams(current); for (const [key, value] of Object.entries(changes)) { if (value === undefined || value === "") next.delete(key); else next.set(key, value); } if (resetPage) next.delete("page"); return next; });
  const setPage = (value: number) => updateQuery({ page: String(value) }, false);
  useEffect(() => setSearch(query), [query]);
  const [variantId, setVariantId] = useState(0);
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [historyPage, setHistoryPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const products = useResource<ProductPage>(`${stockMax === undefined ? "/products" : "/admin/products"}?page=${page}&page_size=50${query ? `&q=${encodeURIComponent(query)}` : ""}${stockMax === undefined ? "" : `&stock_max=${stockMax}`}`, { scope: user?.id });
  const history = useResource<ReplenishmentPage>(`/admin/replenishments?limit=10&offset=${(historyPage - 1) * 10}`, { scope: user?.id });
  const stockProducts = [...(products.data?.items || []), ...(editorProduct && !products.data?.items.some((product) => product.id === editorProduct.id) ? [editorProduct] : [])];
  const variants = stockProducts.flatMap((product) => product.variants.map((variant) => ({ ...variant, productName: product.name })));
  const selected = variants.find((variant) => variant.id === variantId) || variants[0];
  useEffect(() => {
    if (focusStock && !products.loading && selected?.id === variantId) {
      document.getElementById("replenishment-quantity")?.focus();
      setFocusStock(false);
    }
  }, [focusStock, products.loading, selected?.id, variantId]);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected || busy) return;
    const amount = Number(quantity);
    if (!Number.isSafeInteger(amount) || amount < 1) { setError("Укажите целое положительное количество."); return; }
    if (reason.trim().length < 3) { setError("Укажите причину пополнения."); return; }
    setBusy(true); setError(""); setSuccess("");
    try {
      const record = await api<Replenishment>(`/admin/variants/${selected.id}/replenishments`, { method: "POST", body: json({ quantity: amount, reason: reason.trim() }) });
      setSuccess(`Пополнено на ${record.quantity} шт. Новый остаток: ${record.stock_after} шт.`);
      setQuantity(""); setReason(""); products.reload(); history.reload();
    } catch (problem) { setError(messageOf(problem)); }
    finally { setBusy(false); }
  };
  return <section>
    <PageTitle eyebrow="Каталог и склад" subtitle="Создавайте товары, меняйте их данные и цены. Пополнение фиксируется в истории склада.">Товары и остатки</PageTitle>
    <div className="button-row"><button type="button" className="button" disabled={editorBusy} onClick={() => { setEditingId(null); setEditorRevision((value) => value + 1); }}>Добавить товар</button></div>
    <form className="admin-search" role="search" onSubmit={(event) => { event.preventDefault(); updateQuery({ q: search.trim() }); setVariantId(0); }}><label className="field"><span>Товар, питомец или артикул</span><input type="search" maxLength={100} value={search} onChange={(event) => setSearch(event.target.value)} /></label><button className="button outline">Найти</button></form>
    <div className="admin-stock-filter"><label className="admin-checkbox"><input type="checkbox" checked={stockMax !== undefined} onChange={(event) => { updateQuery({ stock_max: event.target.checked ? "5" : undefined }); setVariantId(0); }} /> Только с малым остатком</label>{stockMax !== undefined && <label className="field"><span>Остаток одного из вариантов не более, шт.</span><input key={stockMax} type="number" min={0} max={2147483647} step={1} defaultValue={stockMax} onBlur={(event) => { const value = Number(event.target.value); if (event.target.value !== "" && Number.isInteger(value) && value >= 0 && value <= 2147483647) updateQuery({ stock_max: String(value) }); else event.target.value = String(stockMax); }} /></label>}</div>
    <ExportControls dataset="products" filters={{ q: query, stock_max: stockMax }} title="Каталог и остатки" />
    {editingId !== undefined && <ProductEditor key={`${editingId ?? "new"}-${editorRevision}`} productId={editingId} onBusyChange={setEditorBusy} onClose={() => { if (!editorBusy) { setEditingId(undefined); setEditorProduct(null); } }} onSaved={(fresh) => { setEditorProduct(fresh); products.reload(); }} onReplenish={(id) => { setVariantId(id); setFocusStock(true); }} />}
    {products.loading ? <Loading text="Загружаем товары…" /> : products.error ? <ErrorNotice message={products.error} retry={products.reload} /> : products.data ? <>
      <p className="form-note">Найдено товаров: {products.data.total}</p>
      {products.data.items.length > 0 && <div className="admin-table-wrap"><table className="admin-table admin-product-table"><thead><tr><th>Товар</th><th>Для кого / раздел</th><th>Варианты</th><th>Цена от</th><th>Управление</th></tr></thead><tbody>{products.data.items.map((product) => <tr key={product.id}><td><strong>{product.name}</strong><br /><small>{product.brand}</small></td><td>{PETS.find((pet) => pet.id === product.pet_type)?.label}<br /><small>{product.product_kind ? PRODUCT_KINDS[product.product_kind] : "Раздел не указан"}</small></td><td>{product.variants.length}<br /><small>Остаток {product.variants.reduce((sum, variant) => sum + variant.stock, 0)} шт.</small></td><td>{money(Math.min(...product.variants.map((variant) => Number(variant.price))))}</td><td><button type="button" className="text-button" disabled={editorBusy} onClick={() => { setEditingId(product.id); setEditorProduct(product); setEditorRevision((value) => value + 1); }}>Редактировать<span className="visually-hidden"> {product.name}</span></button><Link className="text-link" to={`/product/${product.id}`}>На сайте ↗</Link></td></tr>)}</tbody></table></div>}
      {selected ? <form className="admin-stock-form" onSubmit={(event) => void submit(event)}><h2>Пополнить остаток</h2>
        <label className="field"><span>Вариант товара</span><select value={selected.id} onChange={(event) => { setVariantId(Number(event.target.value)); setError(""); setSuccess(""); }}>{variants.map((variant) => <option key={variant.id} value={variant.id}>{variant.productName} · {variant.label} · {variant.sku} · остаток {variant.stock} шт.</option>)}</select></label>
        <div className="admin-stock-fields"><label className="field"><span>Добавить, шт.</span><input id="replenishment-quantity" type="number" min={1} step={1} required value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label><label className="field"><span>Причина</span><input type="text" required maxLength={300} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Например, новая поставка" /></label></div>
        <ErrorNotice message={error} />{success && <p role="status" className="success-text">{success}</p>}
        <button className="button" disabled={busy}>{busy ? "Пополняем…" : "Добавить к остатку"}</button>
      </form> : <p className="form-note">На этой странице нет вариантов товара.</p>}
      {products.data.total > 50 && <nav className="pagination" aria-label="Страницы товаров"><button className="button outline" disabled={page <= 1} onClick={() => { setPage(page - 1); setVariantId(0); }}>Назад</button><span>{page} / {Math.ceil(products.data.total / 50)}</span><button className="button outline" disabled={page * 50 >= products.data.total} onClick={() => { setPage(page + 1); setVariantId(0); }}>Дальше</button></nav>}
    </> : null}
    <section className="admin-history" aria-labelledby="replenishment-title"><h2 id="replenishment-title">История пополнений</h2><p className="form-note">Здесь показаны только добавления товара, без списаний при заказах.</p>
      <ExportControls dataset="replenishments" title="Выгрузка пополнений" />
      {history.loading ? <Loading text="Загружаем историю…" /> : history.error ? <ErrorNotice message={history.error} retry={history.reload} /> : history.data?.items.length ? <><div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Когда</th><th>Товар и вариант</th><th>Добавлено</th><th>Остаток</th><th>Причина</th></tr></thead><tbody>{history.data.items.map((item) => <tr key={item.id}><td>{dateTime(item.created_at)}</td><td>{item.product_name} · {item.variant_label}<br /><small>{item.sku}</small></td><td>+{item.quantity}</td><td>{item.stock_before} → {item.stock_after}</td><td>{item.reason}</td></tr>)}</tbody></table></div>{history.data.total > 10 && <nav className="pagination" aria-label="Страницы пополнений"><button className="button outline" disabled={historyPage <= 1} onClick={() => setHistoryPage(historyPage - 1)}>Назад</button><span>{historyPage} / {Math.ceil(history.data.total / 10)}</span><button className="button outline" disabled={historyPage * 10 >= history.data.total} onClick={() => setHistoryPage(historyPage + 1)}>Дальше</button></nav>}</> : <p>Пополнений пока нет.</p>}
    </section>
  </section>;
}

export function AdminReviews() { return <AdminReviewModeration />; }

export function AdminUsers() {
  const { user } = useStore();
  const [params, setParams] = useSearchParams();
  const page = adminPage(params);
  const setPage = (value: number) => setParams(value <= 1 ? {} : { page: String(value) });
  const users = useResource<{ items: User[]; total: number; limit: number; offset: number }>(`/admin/users/page?limit=50&offset=${(page - 1) * 50}`, { scope: user?.id });
  const pages = Math.max(1, Math.ceil((users.data?.total || 0) / 50));
  return <section><PageTitle eyebrow="Учётные записи" subtitle="Список пользователей магазина. Права и активность определяются сервером.">Пользователи</PageTitle>
    <ExportControls dataset="users" />
    {users.loading ? <Loading text="Загружаем пользователей…" /> : users.error ? <ErrorNotice message={users.error} retry={users.reload} /> : users.data?.items.length ? <><p className="form-note">Всего пользователей: {users.data.total}</p><div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Пользователь</th><th>Email</th><th>Роль</th><th>Состояние</th></tr></thead><tbody>{users.data.items.map((user) => <tr key={user.id}><td>{user.first_name} {user.last_name || ""}</td><td>{user.email}</td><td>{user.role === "admin" ? "Администратор" : "Покупатель"}</td><td>{user.is_active ? "Активен" : "Отключён"}</td></tr>)}</tbody></table></div></> : <p className="form-note">{page > 1 ? "На этой странице пользователей нет. Вернитесь к предыдущей странице." : "Пользователей пока нет."}</p>}
    {!users.error && (page > 1 || pages > 1) && <nav className="pagination" aria-label="Страницы пользователей"><button className="button outline" disabled={page === 1 || users.loading} onClick={() => setPage(page - 1)}>Назад</button><span>Страница {page}{page <= pages ? ` / ${pages}` : ""}</span><button className="button outline" disabled={page >= pages || users.loading} onClick={() => setPage(page + 1)}>Дальше</button></nav>}
  </section>;
}

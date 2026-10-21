import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router";
import { api, json, messageOf } from "../api";
import { Breadcrumbs, ErrorNotice, Loading, PageTitle } from "../components";
import { useStore } from "../StoreContext";
import type { Product, ProductPage } from "../types";
import { useResource } from "../useResource";
import { ExportControls } from "../ExportControls";

function localDate(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

export default function Discounts() {
  const { user } = useStore();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const products = useResource<ProductPage>(user?.role === "admin" ? `/products?page_size=50&page=${page}${query ? `&q=${encodeURIComponent(query)}` : ""}` : null);
  const [productId, setProductId] = useState(0);
  const [percent, setPercent] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const selected = products.data?.items.find((product) => product.id === productId) || products.data?.items[0];
  useEffect(() => {
    if (!selected) return;
    setProductId(selected.id);
    setPercent(selected.discount_percent ? String(selected.discount_percent) : "");
    setStart(localDate(selected.discount_start_at));
    setEnd(localDate(selected.discount_end_at));
  }, [selected?.id, selected?.discount_percent, selected?.discount_start_at, selected?.discount_end_at]);

  if (user?.role !== "admin") return <div className="empty-state"><h1>Доступ только для администратора</h1><Link className="button" to="/">На главную</Link></div>;
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected || busy) return;
    const value = Number(percent);
    if (!Number.isInteger(value) || value < 1 || value > 90) { setError("Укажите скидку от 1 до 90%. "); return; }
    if (start && end && new Date(end).getTime() <= new Date(start).getTime()) { setError("Окончание акции должно быть позже начала."); return; }
    setBusy(true); setError(""); setSuccess("");
    try {
      await api<Product>(`/admin/products/${selected.id}/discount`, { method: "PUT", body: json({ percent: value, ...(start ? { start_at: new Date(start).toISOString() } : {}), ...(end ? { end_at: new Date(end).toISOString() } : {}) }) });
      setSuccess("Скидка сохранена.");
      products.reload();
    } catch (problem) { setError(messageOf(problem)); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    if (!selected || busy) return;
    setBusy(true); setError(""); setSuccess("");
    try {
      await api<void>(`/admin/products/${selected.id}/discount`, { method: "DELETE" });
      setSuccess("Скидка удалена.");
      products.reload();
    } catch (problem) { setError(messageOf(problem)); }
    finally { setBusy(false); }
  };
  return <>
    <Breadcrumbs items={[{ label: "Личный кабинет", to: "/account" }, { label: "Управление скидками" }]} />
    <PageTitle eyebrow="Для администратора" subtitle="Назначьте скидку товару и срок её действия.">Скидки</PageTitle>
    <form className="discount-search" role="search" onSubmit={(event) => { event.preventDefault(); setQuery(search.trim()); setPage(1); setProductId(0); }}>
      <label className="field"><span>Найти товар по названию или артикулу</span><input type="search" maxLength={100} value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      <button type="submit" className="button outline">Найти</button>
    </form>
    <ExportControls dataset="discounts" filters={{ q: query }} />
    {products.data && <p className="form-note">Найдено товаров: {products.data.total}. Страница {page} из {Math.max(1, Math.ceil(products.data.total / 50))}.</p>}
    {products.loading ? <Loading text="Загружаем товары…" /> : products.error ? <ErrorNotice message={products.error} retry={products.reload} /> : !selected ? <p>Товаров пока нет.</p> :
      <form className="discount-admin-form" onSubmit={(event) => void save(event)}>
        <label className="field"><span>Товар</span><select value={selected.id} onChange={(event) => { setProductId(Number(event.target.value)); setError(""); setSuccess(""); }}>
          {products.data?.items.map((product) => <option value={product.id} key={product.id}>{product.name}</option>)}
        </select></label>
        <div className="form-row">
          <label className="field"><span>Скидка, %</span><input type="number" min="1" max="90" step="1" required value={percent} onChange={(event) => setPercent(event.target.value)} /></label>
          <label className="field"><span>Начало (необязательно)</span><input type="datetime-local" value={start} onChange={(event) => setStart(event.target.value)} /></label>
          <label className="field"><span>Окончание (необязательно)</span><input type="datetime-local" value={end} onChange={(event) => setEnd(event.target.value)} /></label>
        </div>
        <p className="form-note">Указанное время преобразуется в UTC. Скидка применяется ко всем вариантам товара. Цена уже созданных заказов не меняется.</p>
        <ErrorNotice message={error} />
        {success && <p role="status" className="success-text">{success}</p>}
        <div className="button-row"><button type="submit" className="button" disabled={busy}>{busy ? "Сохраняем…" : "Сохранить скидку"}</button>
          {selected.discount_percent != null && <button type="button" className="button outline" disabled={busy} onClick={() => void remove()}>Убрать скидку</button>}</div>
      </form>}
    {products.data && products.data.total > 50 && <nav className="pagination" aria-label="Страницы товаров для скидок">
      <button type="button" className="button outline" disabled={page <= 1 || products.loading} onClick={() => { setPage((value) => value - 1); setProductId(0); }}>Назад</button>
      <span>{page} / {Math.ceil(products.data.total / 50)}</span>
      <button type="button" className="button outline" disabled={page * 50 >= products.data.total || products.loading} onClick={() => { setPage((value) => value + 1); setProductId(0); }}>Дальше</button>
    </nav>}
  </>;
}

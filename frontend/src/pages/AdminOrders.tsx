import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { Breadcrumbs, ErrorNotice, Loading, PageTitle, PriceLabel } from "../components";
import { validPoint } from "../geo";
import type { GeoPoint } from "../geo";
import { MapView } from "../MapView";
import { money } from "../lib";
import { useStore } from "../StoreContext";
import type { AdminOrder, AdminOrderPage } from "../types";
import { useResource } from "../useResource";
import { orderStatus } from "./Account";
import { ExportControls } from "../ExportControls";
import { api, ApiError, json, messageOf } from "../api";
import { useOrderResource } from "../useOrderResource";
import DeliveryTracking, { DeliveryConnection } from "../DeliveryTracking";
import { deliveryStages, incidentLabels, isOrderTerminal, isPaymentReady, nextDeliveryStage } from "../delivery";
import type { DeliveryCommand, DeliveryIncident } from "../types";
import { adminPage, orderFilters, orderQuery, ORDER_QUEUES } from "../adminFilters";

const dateTime = (value: string) => new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));

function AccessDenied() {
  return <div className="empty-state"><h1>Доступ только для администратора</h1><Link className="button" to="/account">В личный кабинет</Link></div>;
}

export default function AdminOrders() {
  const { user } = useStore();
  const [params, setParams] = useSearchParams();
  const page = adminPage(params);
  const filters = orderFilters(params);
  const update = (name: string, value: string) => setParams((current) => { const next = new URLSearchParams(current); if (value) next.set(name, value); else next.delete(name); next.delete("page"); return next; });
  const setPage = (value: number) => setParams((current) => { const next = new URLSearchParams(current); if (value > 1) next.set("page", String(value)); else next.delete("page"); return next; });
  const limit = 20;
  const query = orderQuery(filters, page, limit);
  const orders = useResource<AdminOrderPage>(user?.role === "admin" ? `/admin/orders?${query}` : null, { scope: user?.id });
  if (user?.role !== "admin") return <AccessDenied />;
  return <>
    <Breadcrumbs items={[{ label: "Личный кабинет", to: "/account" }, { label: "Заказы магазина" }]} />
    <PageTitle eyebrow="Для администратора" subtitle="Адрес и выбранная точка доставки доступны в карточке заказа.">Заказы магазина</PageTitle>
    <nav className="admin-queue-tabs" aria-label="Очереди заказов"><Link to="/admin/orders" aria-current={!filters.queue ? "page" : undefined}>Все заказы</Link>{ORDER_QUEUES.map(([id, label]) => <Link key={id} to={`/admin/orders?queue=${id}`} aria-current={filters.queue === id ? "page" : undefined}>{label}</Link>)}</nav>
    <details className="admin-filter-options"><summary>Уточнить условия{Object.keys(filters).filter((key) => key !== "queue").length ? ` · задано ${Object.keys(filters).filter((key) => key !== "queue").length}` : ""}</summary>
    <div className="admin-order-filters">
      <label className="field"><span>Состояние</span><select aria-label="Состояние" value={filters.status || ""} onChange={(event) => update("status", event.target.value)}>
        <option value="">Все</option><option value="created">Активные</option><option value="cancelled">Отменённые</option>
      </select></label>
      <label className="field"><span>Оплата</span><select aria-label="Оплата" value={filters.payment_status || ""} onChange={(event) => update("payment_status", event.target.value)}>
        <option value="">Любая</option><option value="pending">Ожидает тестовой оплаты</option><option value="demo_paid">Тестовая оплата прошла</option><option value="failed">Тестовая оплата не прошла</option><option value="cod_pending">При получении</option><option value="cancelled">Отменена</option>
      </select></label>
      <label className="field"><span>Получение</span><select aria-label="Получение" value={filters.delivery_method || ""} onChange={(event) => update("delivery_method", event.target.value)}>
        <option value="">Любое</option><option value="delivery">Доставка</option><option value="pickup">Самовывоз</option>
      </select></label>
      <label className="field"><span>Этап доставки</span><select aria-label="Этап доставки" value={filters.delivery_stage || ""} onChange={(event) => update("delivery_stage", event.target.value)}><option value="">Любой</option>{deliveryStages.map((stage) => <option key={stage.id} value={stage.id}>{stage.label}</option>)}</select></label>
      <label className="field"><span>Проблема доставки</span><select aria-label="Проблема доставки" value={filters.delivery_incident || ""} onChange={(event) => update("delivery_incident", event.target.value)}><option value="">Любая</option>{Object.entries(incidentLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      <label className="field"><span>Подтверждение получения</span><select aria-label="Подтверждение получения" value={filters.received === undefined ? "" : String(filters.received)} onChange={(event) => update("received", event.target.value)}><option value="">Все</option><option value="false">Ещё не получены</option><option value="true">Получены</option></select></label>
      <label className="field"><span>Доставка без обновления</span><select aria-label="Доставка без обновления" value={filters.stale_hours || ""} onChange={(event) => update("stale_hours", event.target.value)}><option value="">Не учитывать</option><option value="6">Более 6 часов</option><option value="24">Более суток</option><option value="48">Более двух суток</option><option value="168">Более недели</option></select></label>
    </div>
    </details>
    {Object.keys(filters).length > 0 && <Link className="text-link" to="/admin/orders">Сбросить все условия</Link>}
    <ExportControls dataset="orders" filters={filters} />
    {orders.loading ? <Loading text="Загружаем заказы…" /> : orders.error ? <ErrorNotice message={orders.error} retry={orders.reload} /> : orders.data?.items.length ? <>
      <p className="form-note">Всего заказов: {orders.data.total}</p>
      <div className="admin-order-list">{orders.data.items.map((order) => <Link className="admin-order-row" key={order.id} to={`/admin/orders/${order.id}`}>
        <div><strong>Заказ №{order.id}</strong><small>{dateTime(order.created_at)} · {order.customer_first_name || order.contact_name}</small></div>
        <div><span>{order.delivery_method === "delivery" ? "Доставка" : "Самовывоз"}</span><small>{order.address || "Без адреса"}</small>{order.delivery_lat != null && order.delivery_lon != null && <small>Точка на карте указана</small>}</div>
        <div><span className={`status-badge ${order.received_at ? "success" : ""}`}>{orderStatus(order)}</span>{order.delivery_tracking && <small>{deliveryStages.find((stage) => stage.id === order.delivery_tracking!.stage)?.label}{order.delivery_tracking.incident ? ` · ${incidentLabels[order.delivery_tracking.incident]}` : ""}</small>}</div>
        <strong>{money(order.total)}</strong>
        <span aria-hidden="true">↗</span>
      </Link>)}</div>
      {orders.data.total > limit && <nav className="pagination" aria-label="Страницы заказов">
        <button type="button" className="button outline" disabled={page <= 1 || orders.loading} onClick={() => setPage(page - 1)}>Назад</button>
        <span>{page} / {Math.ceil(orders.data.total / limit)}</span>
        <button type="button" className="button outline" disabled={page * limit >= orders.data.total || orders.loading} onClick={() => setPage(page + 1)}>Дальше</button>
      </nav>}
    </> : <p className="form-note">По выбранным условиям заказов нет.</p>}
    {!orders.loading && !orders.error && !orders.data?.items.length && page > 1 && <nav className="pagination" aria-label="Страницы заказов"><button className="button outline" onClick={() => setPage(page - 1)}>Назад</button><span>Страница {page}</span></nav>}
  </>;
}

export function AdminOrderDetail() {
  const { user } = useStore();
  const { id } = useParams();
  const order = useOrderResource<AdminOrder>(user?.role === "admin" && id ? `/admin/orders/${id}` : null, user?.id);
  const [deliveryError, setDeliveryError] = useState("");
  const [incident, setIncident] = useState<DeliveryIncident>("flat_tire");
  const [incidentNote, setIncidentNote] = useState("");
  useEffect(() => { setDeliveryError(""); setIncidentNote(""); setIncident("flat_tire"); }, [id]);
  const command = async (input: DeliveryCommand) => {
    if (order.mutating) return;
    setDeliveryError("");
    try {
      await order.mutate((signal) => api<AdminOrder>(`/admin/orders/${id}/delivery`, {
        method: "PATCH", signal, body: json(input),
      }));
      setIncidentNote("");
    } catch (error) {
      setDeliveryError(messageOf(error));
      if (error instanceof ApiError && error.status === 409) order.reload();
    }
  };
  if (user?.role !== "admin") return <AccessDenied />;
  if (order.loading) return <Loading text="Загружаем заказ…" />;
  if (order.error) return <ErrorNotice message={order.error} retry={order.reload} />;
  const data = order.data;
  if (!data) return null;
  const tracking = data.delivery_tracking;
  const nextStage = tracking ? nextDeliveryStage(tracking.stage) : null;
  const canManageDelivery = Boolean(tracking) && !isOrderTerminal(data);
  const coordinate: GeoPoint | null = data.delivery_lat != null && data.delivery_lon != null
    ? { lat: Number(data.delivery_lat), lon: Number(data.delivery_lon) } : null;
  const point = coordinate && validPoint(coordinate) ? coordinate : null;
  return <>
    <Breadcrumbs items={[{ label: "Заказы магазина", to: "/admin/orders" }, { label: `Заказ №${data.id}` }]} />
    <PageTitle eyebrow="Заказ магазина" subtitle={`Создан ${dateTime(data.created_at)}`}>Заказ №{data.id}</PageTitle>
    <div className="admin-order-detail">
      <section className="admin-order-main">
        <DeliveryConnection error={order.refreshError} refreshing={order.refreshing} retry={order.reload} />
        <div className="admin-order-status"><span className={`status-badge ${data.received_at ? "success" : ""}`}>{orderStatus(data)}</span>
          {data.paid_at && <p>Оплачен: {dateTime(data.paid_at)}</p>}
          {data.received_at && <p>Получение подтверждено: {dateTime(data.received_at)}</p>}
          <button type="button" className="text-button" disabled={order.refreshing || order.mutating} onClick={order.reload}>{order.refreshing ? "Обновляем…" : "Обновить сведения"}</button>
        </div>
        <DeliveryTracking order={data} />
        {canManageDelivery && tracking && <section className="delivery-admin-controls" aria-label="Управление доставкой" aria-busy={order.mutating}>
          <h2>Управление доставкой</h2>
          <p className="form-note">Изменения сразу видны покупателю. Страница проверяет обновления каждые 10 секунд.</p>
          {!isPaymentReady(data) && <p className="form-note">Отправка доступна после успешной тестовой оплаты. Проблему на складе можно отметить сейчас.</p>}
          {nextStage && <button type="button" className="button" disabled={order.mutating || Boolean(tracking.incident) || !isPaymentReady(data)} onClick={() => void command({ expected_version: tracking.version, stage: nextStage })}>
            {order.mutating ? "Сохраняем…" : `Перевести: ${deliveryStages.find((stage) => stage.id === nextStage)?.label}`}
          </button>}
          {tracking.incident ? <>
            <p className="form-note">Сначала устраните отмеченную проблему. После этого можно продолжить доставку.</p>
            <button type="button" className="button outline" disabled={order.mutating} onClick={() => void command({ expected_version: tracking.version, incident: null })}>{order.mutating ? "Сохраняем…" : "Проблема устранена · продолжить"}</button>
          </> : <form onSubmit={(event) => { event.preventDefault(); void command({ expected_version: tracking.version, incident, incident_note: incidentNote.trim() || null }); }}>
            <label className="field"><span>Проблема с доставкой</span><select value={incident} disabled={order.mutating} onChange={(event) => setIncident(event.target.value as DeliveryIncident)}><option value="flat_tire">{incidentLabels.flat_tire}</option><option value="overturned">{incidentLabels.overturned}</option><option value="engine_failure">{incidentLabels.engine_failure}</option></select></label>
            <label className="field"><span>Комментарий для покупателя</span><textarea value={incidentNote} disabled={order.mutating} maxLength={500} onChange={(event) => setIncidentNote(event.target.value)} placeholder="Например, меняем колесо. Этап доставки сохранён." /></label>
            <button type="submit" className="button outline" disabled={order.mutating}>{order.mutating ? "Сохраняем…" : "Отметить проблему"}</button>
          </form>}
          <ErrorNotice message={deliveryError} />
        </section>}
        <section className="order-items"><h2>Товары</h2>{data.items.map((item) => <div key={item.variant_id}>
          <span><Link to={`/product/${item.product_id}`}>{item.product_name}</Link><small>{item.variant_label} · {item.quantity} шт.</small>
            <small>За шт.: <PriceLabel variant={{ price: item.unit_price, original_price: item.original_unit_price }} /></small></span>
          <strong>{money(item.line_total)}</strong>
        </div>)}</section>
      </section>
      <aside className="admin-order-side">
        <h2>Покупатель и доставка</h2>
        <dl className="admin-order-details">
          <div><dt>Аккаунт</dt><dd>{data.customer_first_name} · {data.customer_email}</dd></div>
          <div><dt>Получатель</dt><dd>{data.contact_name || "Не указан"}</dd></div>
          <div><dt>Телефон</dt><dd>{data.phone || "Не указан"}</dd></div>
          <div><dt>Способ получения</dt><dd>{data.delivery_method === "delivery" ? "Доставка" : "Самовывоз"}</dd></div>
          {data.address && <div><dt>Адрес доставки</dt><dd>{data.address}</dd></div>}
          {data.comment && <div><dt>Комментарий покупателя</dt><dd>{data.comment}</dd></div>}
          <div><dt>Способ оплаты</dt><dd>{data.payment_method === "demo" ? "Тестовая" : "При получении"}</dd></div>
          <div><dt>Итого</dt><dd><strong>{money(data.total)}</strong></dd></div>
        </dl>
        {data.delivery_method === "delivery" && <div className="admin-delivery-point">
          <h3>Точка доставки</h3>
          {point ? <><MapView label="Выбранная покупателем точка доставки" center={point} selected={point} zoom={14} />
            <p className="form-note">Координаты: {point.lat.toFixed(7)}, {point.lon.toFixed(7)}. Это выбранная точка, не отслеживание курьера.</p>
            <a className="text-link" href={`https://www.openstreetmap.org/?mlat=${point.lat}&mlon=${point.lon}#map=17/${point.lat}/${point.lon}`} target="_blank" rel="noopener noreferrer">Открыть в OpenStreetMap ↗</a></>
            : <p className="form-note">Покупатель указал адрес без точки на карте.</p>}
        </div>}
      </aside>
    </div>
  </>;
}

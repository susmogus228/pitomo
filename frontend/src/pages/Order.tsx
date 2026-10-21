import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api, json, messageOf } from "../api";
import {
  Breadcrumbs,
  ErrorNotice,
  Icon,
  Loading,
  PageTitle,
  PriceLabel,
} from "../components";
import { dateLabel, money } from "../lib";
import type { Order } from "../types";
import { useOrderResource } from "../useOrderResource";
import DeliveryTracking, { DeliveryConnection } from "../DeliveryTracking";
import { canCancelOrder, canReceiveOrder } from "../delivery";
import { orderStatus } from "./Account";
import { useStore } from "../StoreContext";
import RepeatOrder from "../RepeatOrder";

export default function OrderPage() {
  const { id } = useParams();
  const { user } = useStore();
  const resource = useOrderResource<Order>(
    id ? `/orders/${id}` : null,
    user?.id,
  );
  const busy = resource.mutating;
  const [error, setError] = useState("");
  const [confirmCancel, setConfirmCancel] = useState(false);
  useEffect(() => {
    setError("");
    setConfirmCancel(false);
  }, [id]);
  const action = async (kind: "success" | "failure" | "cancel" | "receive") => {
    if (busy) return;
    setError("");
    try {
      await resource.mutate((signal) =>
        api<Order>(
          `/orders/${id}/${kind === "cancel" ? "cancel" : kind === "receive" ? "confirm-receipt" : "demo-payment"}`,
          {
            method: "POST",
            signal,
            ...(kind === "success" || kind === "failure"
              ? { body: json({ outcome: kind }) }
              : {}),
          },
        ),
      );
      setConfirmCancel(false);
    } catch (e) {
      setError(messageOf(e));
    }
  };
  if (resource.loading) return <Loading text="Загружаем заказ…" />;
  if (resource.error)
    return <ErrorNotice message={resource.error} retry={resource.reload} />;
  const order = resource.data;
  if (!order) return null;
  const cancelled =
    order.status === "cancelled" || order.payment_status === "cancelled";
  const paid = order.payment_status === "demo_paid";
  const received = Boolean(order.received_at);
  return (
    <>
      <Breadcrumbs
        items={[
          { label: "Мои заказы", to: "/account?tab=orders" },
          { label: `Заказ №${order.id}` },
        ]}
      />
      <PageTitle
        eyebrow={
          cancelled
            ? "Заказ отменён"
            : paid
              ? "Всё получилось"
              : "Заказ сохранён"
        }
        subtitle={`От ${dateLabel(order.created_at)}`}
      >
        Заказ №{order.id}
      </PageTitle>
      <div className="checkout-layout">
        <div className="order-content">
          <DeliveryConnection
            error={resource.refreshError}
            refreshing={resource.refreshing}
            retry={resource.reload}
          />
          <div className={`order-status-panel ${paid ? "paid" : ""}`}>
            <span className="status-badge">{orderStatus(order)}</span>
            <h2>
              {cancelled
                ? "Может быть, в другой раз."
                : received
                  ? "Товары получены."
                  : paid
                    ? "Можно порадовать питомца."
                    : order.payment_method === "cod"
                      ? "Оплата при получении выбрана."
                      : "Осталось проверить оплату."}
            </h2>
            <p>
              {cancelled
                ? "Резерв товаров снят. Заказ сохранён в истории."
                : received
                  ? "Получение подтверждено. Теперь можно оставить отзывы о товарах из этого заказа."
                  : paid
                    ? "Тестовая оплата завершена. Реальные деньги не списывались."
                    : order.payment_method === "cod"
                      ? "Способ оплаты сохранён в заказе. В демонстрационном магазине выдача не выполняется."
                      : "Выберите исход тестовой операции. Карта и платёжные данные не нужны."}
            </p>
          </div>
          <DeliveryTracking order={order} />
          {!cancelled && !paid && order.payment_method === "demo" && (
            <section className="demo-payment">
              <p className="eyebrow">Только тестовый режим</p>
              <h2>Проверим оплату?</h2>
              <p>
                Сумма теста: <strong>{money(order.total)}</strong>
              </p>
              <div className="payment-actions">
                <button
                  className="button"
                  disabled={busy}
                  onClick={() => void action("success")}
                >
                  {busy
                    ? "Подождите…"
                    : order.payment_status === "failed"
                      ? "Повторить: успешная оплата"
                      : "Тест: успешная оплата"}
                  <Icon name="check" size={19} />
                </button>
                <button
                  className="button outline"
                  disabled={busy}
                  onClick={() => void action("failure")}
                >
                  Тест: отказ оплаты
                </button>
              </div>
              <p className="form-note">
                Деньги не списываются. После отказа можно повторить тест или
                отменить заказ.
              </p>
            </section>
          )}
          {canReceiveOrder(order) && (
            <section className="receipt-section">
              <h2>Товар уже у вас?</h2>
              <p>
                Подтвердите получение только после того, как заказ действительно
                пришёл. После этого откроются отзывы.
              </p>
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() => void action("receive")}
              >
                {busy ? "Подождите…" : "Подтверждаю получение"}
              </button>
            </section>
          )}
          <ErrorNotice message={error} />
          <section className="order-items">
            <h2>Что в заказе</h2>
            {order.items.map((item) => (
              <div key={item.variant_id}>
                <span>
                  <Link to={`/product/${item.product_id}`}>
                    {item.product_name}
                  </Link>
                  <small>
                    {item.variant_label} · {item.quantity} шт.
                  </small>
                  {item.original_unit_price &&
                    Number(item.original_unit_price) >
                      Number(item.unit_price) && (
                      <small>
                        За шт.:{" "}
                        <PriceLabel
                          variant={{
                            price: item.unit_price,
                            original_price: item.original_unit_price,
                          }}
                        />
                      </small>
                    )}
                </span>
                <strong>{money(item.line_total)}</strong>
                {received && (
                  <Link
                    className="text-link"
                    to={`/product/${item.product_id}#reviews`}
                  >
                    Оставить отзыв
                  </Link>
                )}
              </div>
            ))}
          </section>
          {canCancelOrder(order) && (
            <div className="cancel-section">
              {confirmCancel ? (
                <div role="group" aria-label="Подтверждение отмены заказа">
                  <p>Отменить заказ №{order.id}? Товары вернутся в наличие.</p>
                  <div className="button-row">
                    <button
                      className="button danger"
                      disabled={busy}
                      onClick={() => void action("cancel")}
                    >
                      Да, отменить заказ
                    </button>
                    <button
                      className="button outline"
                      disabled={busy}
                      onClick={() => setConfirmCancel(false)}
                    >
                      Оставить заказ
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  className="text-button"
                  onClick={() => setConfirmCancel(true)}
                >
                  Отменить заказ
                </button>
              )}
            </div>
          )}
        </div>
        <aside className="order-summary">
          <h2>Детали заказа</h2>
          <dl className="order-contacts">
            <div>
              <dt>Получатель</dt>
              <dd>{order.contact_name}</dd>
            </div>
            <div>
              <dt>Телефон</dt>
              <dd>{order.phone}</dd>
            </div>
            <div>
              <dt>Получение</dt>
              <dd>
                {order.delivery_method === "delivery"
                  ? "Доставка (демо)"
                  : "Самовывоз (демо)"}
              </dd>
            </div>
            {order.address && (
              <div>
                <dt>Адрес</dt>
                <dd>{order.address}</dd>
              </div>
            )}
            {order.delivery_lat != null && order.delivery_lon != null && (
              <div>
                <dt>Точка доставки</dt>
                <dd>
                  <a
                    className="text-link"
                    href={`https://www.openstreetmap.org/?mlat=${order.delivery_lat}&mlon=${order.delivery_lon}#map=16/${order.delivery_lat}/${order.delivery_lon}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Открыть на карте ↗
                  </a>
                </dd>
              </div>
            )}
            {order.comment && (
              <div>
                <dt>Комментарий</dt>
                <dd>{order.comment}</dd>
              </div>
            )}
            <div>
              <dt>Оплата</dt>
              <dd>
                {order.payment_method === "demo" ? "Тестовая" : "При получении"}
              </dd>
            </div>
            <div className="summary-total">
              <dt>Итого</dt>
              <dd>{money(order.total)}</dd>
            </div>
          </dl>
          <RepeatOrder orderId={order.id} />
          <Link className="button outline full-width" to="/account?tab=orders">
            Все мои заказы
          </Link>
          <Link className="text-link" to="/catalog">
            Вернуться в магазин <Icon name="arrow" size={18} />
          </Link>
        </aside>
      </div>
    </>
  );
}

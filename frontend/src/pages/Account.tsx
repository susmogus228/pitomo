import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { api, json, messageOf } from "../api";
import { Empty, ErrorNotice, Icon, Loading, PageTitle } from "../components";
import { dateLabel, money } from "../lib";
import { useStore } from "../StoreContext";
import type { Order, User } from "../types";
import { useResource } from "../useResource";
import { ConsentSettings } from "../Privacy";
import { deliveryStages, incidentLabels } from "../delivery";
import SavedAddresses from "../SavedAddresses";
import RepeatOrder from "../RepeatOrder";

export const orderStatus = (order: Order) =>
  order.status === "cancelled" || order.payment_status === "cancelled"
    ? "Отменён"
    : order.received_at
      ? "Получен"
      : order.delivery_tracking?.incident
        ? `Задержка: ${incidentLabels[order.delivery_tracking.incident]}`
        : order.delivery_tracking &&
            (order.payment_status === "demo_paid" ||
              order.payment_status === "cod_pending")
          ? deliveryStages.find(
              (stage) => stage.id === order.delivery_tracking?.stage,
            )?.label || "Доставка оформлена"
          : {
              pending: "Ожидает тестовой оплаты",
              demo_paid: "Тестовая оплата прошла",
              failed: "Тестовая оплата не прошла",
              cod_pending: "Оплата при получении",
              cancelled: "Отменён",
            }[order.payment_status] || "Создан";

function Profile() {
  const { user, setUser, logout } = useStore();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setSuccess(false);
    const form = new FormData(event.currentTarget);
    try {
      const next = await api<User>("/users/me", {
        method: "PATCH",
        body: json({
          first_name: String(form.get("first_name")).trim(),
          last_name: String(form.get("last_name")).trim(),
          email: String(form.get("email")).trim(),
        }),
      });
      setUser(next);
      setSuccess(true);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="profile-panel">
      <h2>Личные данные</h2>
      <form
        onSubmit={submit}
        onChange={() => {
          setSuccess(false);
          setError("");
        }}
      >
        <fieldset
          disabled={busy}
          aria-label="Личные данные"
          style={{ border: 0, padding: 0, margin: 0 }}
        >
          <div className="form-row">
            <label className="field">
              <span>Имя</span>
              <input
                name="first_name"
                autoComplete="given-name"
                required
                maxLength={100}
                defaultValue={user?.first_name}
              />
            </label>
            <label className="field">
              <span>Фамилия</span>
              <input
                name="last_name"
                autoComplete="family-name"
                maxLength={100}
                defaultValue={user?.last_name || ""}
              />
            </label>
          </div>
          <label className="field">
            <span>Email</span>
            <input
              name="email"
              type="email"
              autoComplete="email"
              required
              maxLength={254}
              defaultValue={user?.email}
            />
          </label>
          <ErrorNotice message={error} />
          {success && (
            <p className="success-text" role="status">
              Данные сохранены.
            </p>
          )}
          <button className="button" disabled={busy}>
            {busy ? "Сохраняем…" : "Сохранить изменения"}
          </button>
        </fieldset>
      </form>
      <ConsentSettings />
      <div className="profile-logout">
        <button
          className="text-button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await logout();
            } catch (e) {
              setError(messageOf(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          Выйти из аккаунта
        </button>
        <p className="form-note">
          Корзина и заказы останутся в вашем аккаунте.
        </p>
      </div>
    </section>
  );
}

function Orders() {
  const { user } = useStore();
  const [page, setPage] = useState(1);
  const resource = useResource<Order[]>(
    `/orders?limit=10&offset=${(page - 1) * 10}`,
    { scope: user?.id },
  );
  return (
    <section className="orders-panel">
      <h2>История заказов</h2>
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorNotice message={resource.error} retry={resource.reload} />
      ) : resource.data?.length ? (
        <div className="orders-list">
          {resource.data.map((order) => (
            <div className="purchase-history-item" key={order.id}>
              <Link className="order-list-item" to={`/orders/${order.id}`}>
                <div>
                  <h3>Заказ №{order.id}</h3>
                  <p>
                    {dateLabel(order.created_at)} · {order.total_items} шт.
                  </p>
                </div>
                <span
                  className={`status-badge ${order.payment_status === "demo_paid" ? "success" : ""}`}
                >
                  {orderStatus(order)}
                </span>
                <strong>{money(order.total)}</strong>
                <Icon name="arrow" size={20} />
              </Link>
              <RepeatOrder orderId={order.id} compact />
            </div>
          ))}
        </div>
      ) : (
        <Empty
          title={page > 1 ? "Больше заказов нет" : "История начинается здесь"}
        >
          {page > 1
            ? "Вернитесь на предыдущую страницу."
            : "Ваш первый заказ появится здесь сразу после оформления."}
        </Empty>
      )}
      {(page > 1 || (resource.data?.length || 0) === 10) && (
        <div className="pagination">
          <button
            className="button outline"
            disabled={page === 1 || resource.loading}
            onClick={() => setPage((value) => value - 1)}
          >
            Назад
          </button>
          <span>Страница {page}</span>
          <button
            className="button outline"
            disabled={(resource.data?.length || 0) < 10 || resource.loading}
            onClick={() => setPage((value) => value + 1)}
          >
            Дальше
          </button>
        </div>
      )}
    </section>
  );
}

export default function Account() {
  const { user } = useStore();
  const [params, setParams] = useSearchParams();
  const orders = params.get("tab") === "orders";
  const addresses = params.get("tab") === "addresses";
  return (
    <>
      <div className="account-header">
        <PageTitle eyebrow="Ваш уголок в Питомо">
          Привет, {user?.first_name}!
        </PageTitle>
        {user?.role === "admin" && (
          <Link className="account-admin-entry" to="/admin">
            Панель администратора <Icon name="arrow" size={18} />
          </Link>
        )}
      </div>
      <nav className="account-tabs" aria-label="Личный кабинет">
        <button
          className={!orders && !addresses ? "active" : ""}
          aria-current={!orders && !addresses ? "page" : undefined}
          onClick={() => setParams({})}
        >
          Мой профиль
        </button>
        <button
          className={orders ? "active" : ""}
          aria-current={orders ? "page" : undefined}
          onClick={() => setParams({ tab: "orders" })}
        >
          Мои заказы
        </button>
        <button
          className={addresses ? "active" : ""}
          aria-current={addresses ? "page" : undefined}
          onClick={() => setParams({ tab: "addresses" })}
        >
          Мои адреса
        </button>
        <Link to="/favorites">
          Избранное <Icon name="heart" size={18} />
        </Link>
      </nav>
      {orders ? (
        <Orders key={user?.id} />
      ) : addresses ? (
        <SavedAddresses key={user?.id} />
      ) : (
        <Profile key={user?.id} />
      )}
    </>
  );
}

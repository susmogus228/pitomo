import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { api, json, messageOf } from "../api";
import {
  Empty,
  ErrorNotice,
  Icon,
  Loading,
  PageTitle,
  PriceLabel,
} from "../components";
import { cartSignature, clearSubmission, money, submissionKey } from "../lib";
import { DEFAULT_MAP_CENTER } from "../geo";
import { MapView } from "../MapView";
import { AddressSearch } from "../AddressSearch";
import { checkoutAddress } from "../address";
import { useAddressLocation } from "../useAddressLocation";
import { useStore } from "../StoreContext";
import type { CheckoutInput, Order, StorefrontConfig } from "../types";
import { useResource } from "../useResource";
import {
  clearCheckoutDraft,
  readCheckoutDraft,
  saveCheckoutDraft,
} from "../checkoutDraft";
import { checkoutFieldErrors, focusFirstError } from "../formValidation";
import type { FieldErrors } from "../formValidation";
import type { AddressPage } from "../purchaseTypes";
import { savedAddressCheckout } from "../purchaseTypes";

export default function Checkout() {
  const { user, cart, refreshCart, guestMergeBusy, guestMergeUnconfirmed } =
    useStore();
  const navigate = useNavigate();
  const [initialDraft] = useState(() => readCheckoutDraft(user?.id));
  const [draftUserId, setDraftUserId] = useState(user?.id);
  const [draftRestored, setDraftRestored] = useState(Boolean(initialDraft));
  const [draftUnavailable, setDraftUnavailable] = useState(false);
  const [contactName, setContactName] = useState(
    initialDraft?.contactName ??
      [user?.first_name, user?.last_name].filter(Boolean).join(" "),
  );
  const [phone, setPhone] = useState(initialDraft?.phone ?? "");
  const [comment, setComment] = useState(initialDraft?.comment ?? "");
  const [delivery, setDelivery] = useState<"pickup" | "delivery">(
    initialDraft?.delivery ?? "pickup",
  );
  const [payment, setPayment] = useState<"demo" | "cod">(
    initialDraft?.payment ?? "demo",
  );
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [savedAddressId, setSavedAddressId] = useState("");
  const savedAddresses = useResource<AddressPage>(
    user ? "/users/me/addresses" : null,
    { scope: user?.id },
  );
  const defaultApplied = useRef<number | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const address = useAddressLocation(
    initialDraft
      ? { address: initialDraft.address, point: initialDraft.point }
      : undefined,
  );
  const restoreLocation = address.restoreLocation;
  const [addressDetails, setAddressDetails] = useState(
    initialDraft?.details ?? { apartment: "", entrance: "", floor: "" },
  );
  const point = address.point;
  useEffect(() => {
    if (
      !user ||
      draftUserId !== user.id ||
      !savedAddresses.data ||
      defaultApplied.current === user.id
    )
      return;
    defaultApplied.current = user.id;
    if (initialDraft || address.address.trim()) return;
    const selected = savedAddresses.data.items.find((item) => item.is_default);
    if (!selected) return;
    setSavedAddressId(String(selected.id));
    restoreLocation({
      address: savedAddressCheckout(selected),
      point:
        selected.lat !== null && selected.lon !== null
          ? { lat: selected.lat, lon: selected.lon }
          : null,
    });
    setAddressDetails({ apartment: "", entrance: "", floor: "" });
  }, [
    user?.id,
    draftUserId,
    savedAddresses.data,
    address.address,
    restoreLocation,
    initialDraft,
  ]);
  const submitting = useRef(false);
  const completed = useRef(false);
  const config = useResource<StorefrontConfig>("/storefront/config");
  useEffect(() => {
    if (draftUserId === user?.id) return;
    const restored = readCheckoutDraft(user?.id);
    setContactName(
      restored?.contactName ??
        [user?.first_name, user?.last_name].filter(Boolean).join(" "),
    );
    setPhone(restored?.phone ?? "");
    setComment(restored?.comment ?? "");
    setDelivery(restored?.delivery ?? "pickup");
    setPayment(restored?.payment ?? "demo");
    setAddressDetails(
      restored?.details ?? { apartment: "", entrance: "", floor: "" },
    );
    restoreLocation({
      address: restored?.address ?? "",
      point: restored?.point ?? null,
    });
    setDraftRestored(Boolean(restored));
    setSavedAddressId("");
    setFieldErrors({});
    setError("");
    completed.current = false;
    setDraftUserId(user?.id);
  }, [
    user?.id,
    user?.first_name,
    user?.last_name,
    draftUserId,
    restoreLocation,
  ]);
  useEffect(() => {
    if (!user || draftUserId !== user.id || completed.current) return;
    setDraftUnavailable(
      !saveCheckoutDraft(user.id, {
        contactName,
        phone,
        comment,
        delivery,
        payment,
        address: address.address,
        point,
        details: addressDetails,
      }),
    );
  }, [
    user,
    draftUserId,
    contactName,
    phone,
    comment,
    delivery,
    payment,
    address.address,
    point,
    addressDetails,
  ]);
  useEffect(() => {
    if (config.data && !config.data.demo_payments_enabled) setPayment("cod");
  }, [config.data, payment]);
  useEffect(() => {
    void refreshCart()
      .catch((e) => setError(messageOf(e)))
      .finally(() => setLoading(false));
  }, [refreshCart]);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (
      !cart?.can_checkout ||
      guestMergeBusy ||
      guestMergeUnconfirmed ||
      submitting.current ||
      !config.data ||
      draftUserId !== user?.id
    )
      return;
    if (delivery === "delivery" && address.busy) {
      setError("Дождитесь определения адреса или введите его вручную.");
      return;
    }
    if (payment === "demo" && !config.data.demo_payments_enabled) {
      setPayment("cod");
      return;
    }
    setError("");
    const form = new FormData(event.currentTarget);
    const input: CheckoutInput = {
      contact_name: String(form.get("contact_name")).trim(),
      phone: String(form.get("phone")).trim(),
      delivery_method: delivery,
      payment_method: payment,
      ...(delivery === "delivery"
        ? {
            address: checkoutAddress(address.address, addressDetails),
            ...(point
              ? { delivery_lat: point.lat, delivery_lon: point.lon }
              : {}),
          }
        : {}),
      ...(String(form.get("comment") || "").trim()
        ? { comment: String(form.get("comment")).trim() }
        : {}),
    };
    const errors = checkoutFieldErrors(input);
    if (delivery === "delivery" && address.address.trim().length < 5)
      errors.address = "Укажите город, улицу и номер дома.";
    setFieldErrors(errors);
    if (Object.keys(errors).length) {
      focusFirstError(event.currentTarget, errors);
      return;
    }
    submitting.current = true;
    setBusy(true);
    try {
      const key = await submissionKey(
        `${user?.id}|${cartSignature(cart)}|${json(input)}`,
      );
      const order = await api<Order>("/orders", {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: json(input),
      });
      clearSubmission();
      completed.current = true;
      clearCheckoutDraft();
      void refreshCart().catch(() => undefined);
      navigate(`/orders/${order.id}`, { replace: true });
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
      submitting.current = false;
    }
  };
  if (loading || config.loading) return <Loading text="Проверяем корзину…" />;
  if (config.error)
    return <ErrorNotice message={config.error} retry={config.reload} />;
  if (!cart && error)
    return (
      <ErrorNotice
        message={error}
        retry={() =>
          void refreshCart()
            .then(() => setError(""))
            .catch((e) => setError(messageOf(e)))
        }
      />
    );
  if (guestMergeBusy)
    return <Loading text="Проверяем гостевые товары перед оформлением…" />;
  if (guestMergeUnconfirmed)
    return (
      <Empty
        title="Нужно подтвердить объединение корзин"
        action="Проверить корзину"
        to="/cart"
      >
        Ответ на добавление гостевых товаров ещё не подтверждён. Проверьте
        результат, чтобы оформить правильный состав заказа.
      </Empty>
    );
  if (!cart?.items.length)
    return (
      <Empty title="Корзина пока пуста">
        Сначала добавьте товары, которые порадуют питомца.
      </Empty>
    );
  if (!cart.can_checkout)
    return (
      <Empty
        title="Нужно проверить корзину"
        action="Вернуться в корзину"
        to="/cart"
      >
        Количество или наличие товаров изменилось.
      </Empty>
    );
  return (
    <>
      <PageTitle
        eyebrow="Последний шаг"
        subtitle="Укажите контакты и выберите удобный способ."
      >
        Оформление заказа
      </PageTitle>
      <div className="demo-banner">
        <strong>Это демонстрационный заказ.</strong> Деньги не списываются,
        доставка и выдача не выполняются. Не вводите данные банковской карты.
      </div>
      <div className="checkout-layout">
        <form
          id="checkout-form"
          className="checkout-form"
          onSubmit={submit}
          noValidate
          onChange={(event) => {
            const name = (event.target as unknown as HTMLInputElement).name;
            if (fieldErrors[name])
              setFieldErrors((old) => {
                const next = { ...old };
                delete next[name];
                return next;
              });
          }}
        >
          {draftRestored && (
            <p className="success-text" role="status">
              Восстановили черновик заказа из этой вкладки. Он доступен в
              течение 2 часов после последнего изменения. Проверьте данные перед
              оформлением.
            </p>
          )}
          {draftUnavailable && (
            <p className="form-note" role="status">
              Браузер не разрешил сохранить черновик. Не обновляйте страницу до
              оформления заказа.
            </p>
          )}
          <fieldset disabled={busy}>
            <legend>
              <span>01</span> Как к вам обращаться
            </legend>
            <div className="form-row">
              <label className="field">
                <span>Имя и фамилия</span>
                <input
                  name="contact_name"
                  autoComplete="name"
                  value={contactName}
                  onChange={(event) => setContactName(event.target.value)}
                  aria-invalid={Boolean(fieldErrors.contact_name)}
                  aria-describedby={
                    fieldErrors.contact_name ? "checkout-name-error" : undefined
                  }
                  minLength={1}
                  maxLength={100}
                  required
                />
                {fieldErrors.contact_name && (
                  <small className="error-text" id="checkout-name-error">
                    {fieldErrors.contact_name}
                  </small>
                )}
              </label>
              <label className="field">
                <span>Телефон</span>
                <input
                  type="tel"
                  name="phone"
                  autoComplete="tel"
                  placeholder="+7 700 123 45 67"
                  minLength={7}
                  maxLength={32}
                  required
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                  aria-invalid={Boolean(fieldErrors.phone)}
                  aria-describedby={
                    fieldErrors.phone ? "checkout-phone-error" : undefined
                  }
                />
                {fieldErrors.phone && (
                  <small className="error-text" id="checkout-phone-error">
                    {fieldErrors.phone}
                  </small>
                )}
              </label>
            </div>
            <p className="form-note">Email аккаунта: {user?.email}</p>
          </fieldset>
          <fieldset disabled={busy}>
            <legend>
              <span>02</span> Как получить
            </legend>
            <div className="choice-grid">
              <label
                className={`choice-card ${delivery === "pickup" ? "selected" : ""}`}
              >
                <input
                  type="radio"
                  name="delivery_method"
                  value="pickup"
                  checked={delivery === "pickup"}
                  onChange={() => setDelivery("pickup")}
                />
                <span>
                  <strong>Самовывоз</strong>
                  <small>Демонстрационный пункт выдачи</small>
                </span>
              </label>
              <label
                className={`choice-card ${delivery === "delivery" ? "selected" : ""}`}
              >
                <input
                  type="radio"
                  name="delivery_method"
                  value="delivery"
                  checked={delivery === "delivery"}
                  onChange={() => setDelivery("delivery")}
                />
                <span>
                  <strong>Доставка</strong>
                  <small>Проверка оформления с адресом</small>
                </span>
              </label>
            </div>
            {delivery === "delivery" && (
              <>
                {savedAddresses.loading && (
                  <p className="form-note" role="status">
                    Проверяем сохранённые адреса…
                  </p>
                )}
                <ErrorNotice
                  message={savedAddresses.error}
                  retry={savedAddresses.reload}
                />
                {savedAddresses.data &&
                  savedAddresses.data.items.length > 0 && (
                    <label className="field saved-address-select">
                      <span>Сохранённый адрес</span>
                      <select
                        aria-label="Сохранённый адрес"
                        value={savedAddressId}
                        onChange={(event) => {
                          const selected = savedAddresses.data?.items.find(
                            (item) => String(item.id) === event.target.value,
                          );
                          setSavedAddressId(event.target.value);
                          if (!selected) return;
                          restoreLocation({
                            address: savedAddressCheckout(selected),
                            point:
                              selected.lat !== null && selected.lon !== null
                                ? { lat: selected.lat, lon: selected.lon }
                                : null,
                          });
                          setAddressDetails({
                            apartment: "",
                            entrance: "",
                            floor: "",
                          });
                          setFieldErrors((old) => {
                            const next = { ...old };
                            delete next.address;
                            return next;
                          });
                        }}
                      >
                        <option value="">Ввести или изменить вручную</option>
                        {savedAddresses.data.items.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.label}
                            {item.is_default ? " · основной" : ""} —{" "}
                            {savedAddressCheckout(item)}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                <p className="form-note">
                  <Link className="text-link" to="/account?tab=addresses">
                    Управлять моими адресами
                  </Link>{" "}
                  · Изменения ниже применяются только к этому заказу.
                </p>
                <AddressSearch
                  value={address.address}
                  onChange={(value) => {
                    setSavedAddressId("");
                    address.changeAddress(value);
                  }}
                  onSelect={(item) => {
                    setSavedAddressId("");
                    address.selectSuggestion(item);
                  }}
                  enabled={address.geoConfig.data?.enabled === true}
                  configLoading={address.geoConfig.loading}
                  disabled={busy}
                  required
                  error={fieldErrors.address}
                />
                <div className="address-details">
                  <label className="field">
                    <span>Квартира</span>
                    <input
                      type="text"
                      autoComplete="address-line2"
                      maxLength={30}
                      value={addressDetails.apartment}
                      onChange={(event) =>
                        setAddressDetails((old) => ({
                          ...old,
                          apartment: event.target.value,
                        }))
                      }
                      placeholder="Необязательно"
                    />
                  </label>
                  <label className="field">
                    <span>Подъезд</span>
                    <input
                      type="text"
                      maxLength={30}
                      value={addressDetails.entrance}
                      onChange={(event) =>
                        setAddressDetails((old) => ({
                          ...old,
                          entrance: event.target.value,
                        }))
                      }
                      placeholder="Необязательно"
                    />
                  </label>
                  <label className="field">
                    <span>Этаж</span>
                    <input
                      type="text"
                      maxLength={20}
                      value={addressDetails.floor}
                      onChange={(event) =>
                        setAddressDetails((old) => ({
                          ...old,
                          floor: event.target.value,
                        }))
                      }
                      placeholder="Необязательно"
                    />
                  </label>
                </div>
                <div className="delivery-map-block">
                  <div className="delivery-map-heading">
                    <div>
                      <strong>Точка доставки на карте</strong>
                      <p className="form-note">
                        Выбранный адрес появится на карте. Нажмите на карту,
                        чтобы уточнить вход или расположение дома.
                      </p>
                    </div>
                    <button
                      type="button"
                      className="button outline"
                      disabled={address.busy || busy}
                      onClick={() => void address.locate()}
                    >
                      {address.busy ? "Определяем…" : "Моё местоположение"}
                    </button>
                  </div>
                  <MapView
                    label="Карта для выбора точки доставки"
                    center={point || DEFAULT_MAP_CENTER}
                    selected={point}
                    zoom={point ? 13 : 5}
                    disabled={busy || address.busy}
                    onSelect={(next) => void address.selectPoint(next)}
                  />
                  <p className="form-note delivery-point-note" role="status">
                    {address.busy
                      ? "Уточняем адрес точки…"
                      : address.note ||
                        (point
                          ? "Точка доставки выбрана."
                          : "Точка на карте необязательна. Для доставки достаточно полного адреса.")}
                  </p>
                  <ErrorNotice message={address.error} />
                </div>
              </>
            )}
            <label className="field">
              <span>
                Комментарий <small>необязательно</small>
              </span>
              <textarea
                name="comment"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                maxLength={1000}
                rows={3}
                placeholder="Что нужно учесть?"
              />
            </label>
          </fieldset>
          <fieldset disabled={busy}>
            <legend>
              <span>03</span> Как оплатить
            </legend>
            <div className="choice-grid">
              <label
                className={`choice-card ${payment === "demo" ? "selected" : ""}`}
              >
                <input
                  type="radio"
                  name="payment_method"
                  value="demo"
                  disabled={!config.data?.demo_payments_enabled}
                  checked={payment === "demo"}
                  onChange={() => setPayment("demo")}
                />
                <span>
                  <strong>Тестовая оплата</strong>
                  <small>
                    {config.data?.demo_payments_enabled
                      ? "Без карты и списания денег"
                      : "Отключена на сервере"}
                  </small>
                </span>
              </label>
              <label
                className={`choice-card ${payment === "cod" ? "selected" : ""}`}
              >
                <input
                  type="radio"
                  name="payment_method"
                  value="cod"
                  checked={payment === "cod"}
                  onChange={() => setPayment("cod")}
                />
                <span>
                  <strong>При получении</strong>
                  <small>Сохраним выбранный способ</small>
                </span>
              </label>
            </div>
          </fieldset>
          <ErrorNotice message={error} />
          <Link className="text-link" to="/cart">
            <Icon name="back" size={18} /> Назад в корзину
          </Link>
        </form>
        <aside className="order-summary">
          <h2>В вашем заказе</h2>
          <ul className="summary-items">
            {cart.items.map((item) => (
              <li key={item.variant_id}>
                <span>
                  {item.product_name}
                  <small>
                    {item.label} · {item.quantity} шт.
                  </small>
                  {item.original_unit_price &&
                    Number(item.original_unit_price) >
                      Number(item.unit_price) && (
                      <small>
                        <PriceLabel
                          variant={{
                            price: item.unit_price,
                            original_price: item.original_unit_price,
                          }}
                        />{" "}
                        / шт.
                      </small>
                    )}
                </span>
                <strong>{money(item.line_total)}</strong>
              </li>
            ))}
          </ul>
          <dl>
            <div className="summary-total">
              <dt>Итого</dt>
              <dd>{money(cart.subtotal)}</dd>
            </div>
          </dl>
          <button
            className="button full-width"
            type="submit"
            form="checkout-form"
            disabled={busy || (delivery === "delivery" && address.busy)}
          >
            {busy ? "Создаём заказ…" : "Оформить заказ"}
            <Icon name="arrow" size={20} />
          </button>
          <p className="form-note">
            {payment === "demo"
              ? "На следующем экране можно проверить успешную или неуспешную тестовую оплату."
              : "Заказ сохранится с оплатой при получении. Реальная выдача в демонстрации не выполняется."}
          </p>
        </aside>
      </div>
    </>
  );
}

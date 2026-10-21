import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, json, messageOf } from "./api";
import { AddressSearch } from "./AddressSearch";
import { Empty, ErrorNotice, Loading } from "./components";
import { currentPosition, DEFAULT_MAP_CENTER, roundedPoint } from "./geo";
import { MapView } from "./MapView";
import type { AddressInput, AddressPage, SavedAddress } from "./purchaseTypes";
import {
  addressInput,
  savedAddressCheckout,
  savedAddressLine,
} from "./purchaseTypes";
import { useAddressLocation } from "./useAddressLocation";
import { useResource } from "./useResource";
import { useStore } from "./StoreContext";

const blank = (): AddressInput => ({
  label: "",
  city: "",
  street: "",
  house: "",
  details: "",
  lat: null,
  lon: null,
  source: "manual",
  is_default: false,
});

export function SavedAddressForm({
  initial,
  busy,
  onSave,
  onCancel,
}: {
  initial?: SavedAddress;
  busy: boolean;
  onSave: (value: AddressInput) => Promise<void>;
  onCancel: () => void;
}) {
  const [value, setValue] = useState<AddressInput>(
    initial ? addressInput(initial) : blank(),
  );
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState("");
  const address = useAddressLocation(
    initial
      ? {
          address: savedAddressLine(initial),
          point:
            initial.lat !== null && initial.lon !== null
              ? { lat: initial.lat, lon: initial.lon }
              : null,
        }
      : undefined,
  );
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  const manual = (field: "city" | "street" | "house", text: string) => {
    const next = {
      ...value,
      [field]: text,
      lat: null,
      lon: null,
      source: "manual" as const,
    };
    setValue(next);
    address.changeAddress(savedAddressLine(next));
  };
  const selectPoint = (
    point: { lat: number; lon: number },
    source: AddressInput["source"],
  ) => {
    const next = roundedPoint(point);
    setValue((old) => ({ ...old, lat: next.lat, lon: next.lon, source }));
    address.restoreLocation({ address: savedAddressLine(value), point: next });
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || locating) return;
    const next = {
      ...value,
      label: value.label.trim() || "Адрес",
      city: value.city.trim(),
      street: value.street.trim(),
      house: value.house.trim(),
      details: value.details.trim(),
    };
    if (!next.city || !next.street || !next.house) {
      setError("Укажите город, улицу и номер дома.");
      event.currentTarget
        .querySelector<HTMLInputElement>(
          `[name="${!next.city ? "city" : !next.street ? "street" : "house"}"]`,
        )
        ?.focus();
      return;
    }
    setError("");
    await onSave(next);
  };
  return (
    <form className="saved-address-form" onSubmit={submit}>
      <h3 ref={heading} tabIndex={-1}>
        {initial ? "Изменить адрес" : "Новый адрес"}
      </h3>
      <fieldset disabled={busy || locating}>
        <label className="field">
          <span>Название адреса</span>
          <input
            value={value.label}
            onChange={(event) =>
              setValue({ ...value, label: event.target.value })
            }
            maxLength={80}
            placeholder="Например, дом или работа"
          />
        </label>
        <AddressSearch
          value={address.address}
          onChange={(text) => {
            address.changeAddress(text);
            setValue((old) => ({
              ...old,
              city: "",
              street: "",
              house: "",
              lat: null,
              lon: null,
              source: "manual",
            }));
          }}
          onSelect={(item) => {
            address.selectSuggestion(item);
            setValue((old) => ({
              ...old,
              city: item.city || "",
              street: item.street || "",
              house: item.housenumber || "",
              lat: roundedPoint(item).lat,
              lon: roundedPoint(item).lon,
              source: "geoapify",
            }));
          }}
          enabled={address.geoConfig.data?.enabled === true}
          configLoading={address.geoConfig.loading}
          disabled={busy}
          label="Найти адрес в Казахстане"
        />
        <p className="form-note">
          После подсказки проверьте поля ниже. При ручном изменении города,
          улицы или дома старая точка сбрасывается.
        </p>
        <div className="purchase-address-fields">
          <label className="field">
            <span>Город</span>
            <input
              name="city"
              value={value.city}
              required
              maxLength={120}
              autoComplete="address-level2"
              onChange={(event) => manual("city", event.target.value)}
            />
          </label>
          <label className="field">
            <span>Улица</span>
            <input
              name="street"
              value={value.street}
              required
              maxLength={200}
              onChange={(event) => manual("street", event.target.value)}
            />
          </label>
          <label className="field">
            <span>Дом</span>
            <input
              name="house"
              value={value.house}
              required
              maxLength={40}
              onChange={(event) => manual("house", event.target.value)}
            />
          </label>
        </div>
        <label className="field">
          <span>Квартира, подъезд, этаж и другие уточнения</span>
          <input
            value={value.details}
            maxLength={200}
            onChange={(event) =>
              setValue({ ...value, details: event.target.value })
            }
            autoComplete="address-line2"
          />
        </label>
        <details className="purchase-map-details">
          <summary>Уточнить точку на карте · необязательно</summary>
          <button
            type="button"
            className="button outline"
            disabled={busy || locating}
            onClick={async () => {
              setLocating(true);
              setError("");
              try {
                selectPoint(await currentPosition(), "geolocation");
              } catch (problem) {
                setError(messageOf(problem));
              } finally {
                setLocating(false);
              }
            }}
          >
            {locating ? "Определяем…" : "Моё местоположение"}
          </button>
          <MapView
            label="Точка сохранённого адреса"
            center={address.point || DEFAULT_MAP_CENTER}
            selected={address.point}
            onSelect={(point) => selectPoint(point, "map")}
            disabled={busy || locating}
            zoom={address.point ? 13 : 5}
          />
          <p className="form-note">
            {address.point
              ? "Точка выбрана. Проверьте, что она соответствует городу, улице и дому выше."
              : "Точка необязательна. Можно сохранить полный адрес без карты."}
          </p>
        </details>
        <label className="purchase-checkbox">
          <input
            type="checkbox"
            disabled={initial?.is_default}
            checked={value.is_default}
            onChange={(event) =>
              setValue({ ...value, is_default: event.target.checked })
            }
          />
          Использовать по умолчанию
        </label>
        {initial?.is_default && (
          <p className="form-note">
            Чтобы сменить основной адрес, выберите другой в списке адресов.
          </p>
        )}
        <ErrorNotice message={error} />
        <div className="button-row">
          <button className="button" disabled={busy || locating}>
            {busy ? "Сохраняем…" : "Сохранить адрес"}
          </button>
          <button
            type="button"
            className="button outline"
            disabled={busy}
            onClick={onCancel}
          >
            Отмена
          </button>
        </div>
      </fieldset>
    </form>
  );
}

export default function SavedAddresses() {
  const { user } = useStore();
  const owner = useRef(user?.id);
  owner.current = user?.id;
  const resource = useResource<AddressPage>("/users/me/addresses", {
    scope: user?.id,
  });
  const [editing, setEditing] = useState<SavedAddress | "new" | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const addButton = useRef<HTMLButtonElement>(null);
  const finish = () => {
    setEditing(null);
    requestAnimationFrame(() => addButton.current?.focus());
  };
  const mutate = async (request: () => Promise<unknown>, message: string) => {
    if (busy) return;
    const expected = user?.id;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await request();
      if (owner.current !== expected) return;
      resource.reload();
      setSuccess(message);
      setDeleting(null);
      finish();
    } catch (problem) {
      if (owner.current === expected) setError(messageOf(problem));
    } finally {
      if (owner.current === expected) setBusy(false);
    }
  };
  return (
    <section
      className="saved-addresses"
      aria-labelledby="saved-addresses-title"
    >
      <div className="purchase-section-heading">
        <div>
          <h2 id="saved-addresses-title">Мои адреса</h2>
          <p>
            Адреса доступны только в вашем аккаунте. Выберите их при оформлении
            заказа.
          </p>
        </div>
        <button
          ref={addButton}
          className="button"
          disabled={
            busy ||
            (resource.data?.items.length || 0) >= (resource.data?.limit || 20)
          }
          onClick={() => {
            setEditing("new");
            setError("");
            setSuccess("");
          }}
        >
          Добавить адрес
        </button>
      </div>
      <ErrorNotice
        message={error || resource.error}
        retry={resource.error ? resource.reload : undefined}
      />
      {success && (
        <p className="success-text" role="status">
          {success}
        </p>
      )}
      {editing && (
        <SavedAddressForm
          key={editing === "new" ? "new" : editing.id}
          initial={editing === "new" ? undefined : editing}
          busy={busy}
          onCancel={finish}
          onSave={(value) =>
            mutate(
              () =>
                api(
                  editing === "new"
                    ? "/users/me/addresses"
                    : `/users/me/addresses/${editing.id}`,
                  {
                    method: editing === "new" ? "POST" : "PATCH",
                    body: json({ ...value, expected_user_id: user?.id }),
                  },
                ),
              "Адрес сохранён.",
            )
          }
        />
      )}
      {resource.loading ? (
        <Loading text="Загружаем адреса…" />
      ) : resource.data?.items.length ? (
        <div className="saved-address-grid">
          {resource.data.items.map((address) => (
            <article className="saved-address-card" key={address.id}>
              <h3>
                {address.label}{" "}
                {address.is_default && (
                  <span className="status-badge">Основной</span>
                )}
              </h3>
              <p>{savedAddressCheckout(address)}</p>
              <div className="purchase-address-actions">
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() => {
                    setEditing(address);
                    setError("");
                  }}
                >
                  Изменить
                </button>
                {!address.is_default && (
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() =>
                      void mutate(
                        () =>
                          api(`/users/me/addresses/${address.id}`, {
                            method: "PATCH",
                            body: json({
                              is_default: true,
                              expected_user_id: user?.id,
                            }),
                          }),
                        "Основной адрес изменён.",
                      )
                    }
                  >
                    Сделать основным
                  </button>
                )}
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() => setDeleting(address.id)}
                >
                  Удалить
                </button>
              </div>
              {deleting === address.id && (
                <div
                  className="purchase-confirm"
                  role="group"
                  aria-label="Удаление адреса"
                >
                  <p>Удалить адрес «{address.label}»?</p>
                  <div className="button-row">
                    <button
                      className="button danger"
                      disabled={busy}
                      onClick={() =>
                        void mutate(
                          () =>
                            api(`/users/me/addresses/${address.id}`, {
                              method: "DELETE",
                            }),
                          "Адрес удалён.",
                        )
                      }
                    >
                      Да, удалить
                    </button>
                    <button
                      className="button outline"
                      disabled={busy}
                      onClick={() => setDeleting(null)}
                    >
                      Оставить
                    </button>
                  </div>
                </div>
              )}
            </article>
          ))}
        </div>
      ) : (
        !resource.error &&
        !editing && (
          <Empty
            title="Сохранённых адресов пока нет"
            action="Посмотреть товары"
          >
            Добавьте адрес, чтобы не вводить его при следующем заказе.
          </Empty>
        )
      )}
      <p className="form-note">
        Можно сохранить до {resource.data?.limit || 20} адресов. Удаление адреса
        не меняет уже оформленные заказы.
      </p>
    </section>
  );
}

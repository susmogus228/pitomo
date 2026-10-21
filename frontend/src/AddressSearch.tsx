import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { api, messageOf } from "./api";
import { kazakhstanAddresses, LatestAddressRequest } from "./address";
import type { AddressSuggestion } from "./address";
import "./address.css";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSelect: (item: AddressSuggestion) => void;
  enabled: boolean;
  configLoading?: boolean;
  disabled?: boolean;
  required?: boolean;
  label?: string;
  lang?: "ru" | "kk";
  error?: string;
}

export function AddressSearch({
  value,
  onChange,
  onSelect,
  enabled,
  configLoading = false,
  disabled = false,
  required = false,
  label = "Город, улица и дом",
  lang = "ru",
  error: fieldError,
}: Props) {
  const id = useId();
  const [items, setItems] = useState<AddressSuggestion[]>([]);
  const [focused, setFocused] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState("");
  const selectedValue = useRef<string | null>(null);
  const requests = useRef(new LatestAddressRequest());
  const query = value.trim();
  useEffect(() => {
    requests.current.cancel();
    setItems([]);
    setActive(-1);
    setBusy(false);
    setSearched(false);
    setError("");
    if (
      !enabled ||
      disabled ||
      query.length < 3 ||
      !focused ||
      selectedValue.current === value
    )
      return;
    const request = requests.current.start();
    const timer = window.setTimeout(() => {
      setBusy(true);
      void api<{ items: AddressSuggestion[] }>(
        `/geo/address-search?${new URLSearchParams({ q: query, lang, limit: "5" })}`,
        { signal: request.signal },
      )
        .then((data) => {
          if (request.current()) {
            setItems(kazakhstanAddresses(data.items));
            setSearched(true);
            setOpen(true);
          }
        })
        .catch((problem) => {
          if (request.current()) {
            setError(messageOf(problem));
            setOpen(false);
          }
        })
        .finally(() => {
          if (request.current()) setBusy(false);
        });
    }, 450);
    return () => {
      window.clearTimeout(timer);
      requests.current.cancel();
    };
  }, [query, value, enabled, disabled, focused, lang]);
  const select = (item: AddressSuggestion) => {
    requests.current.cancel();
    selectedValue.current = item.label;
    setItems([]);
    setOpen(false);
    setActive(-1);
    setBusy(false);
    setError("");
    onSelect(item);
  };
  const expanded = open && focused && items.length > 0;
  const keydown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      requests.current.cancel();
      setOpen(false);
      setBusy(false);
      setActive(-1);
    } else if (
      (event.key === "ArrowDown" || event.key === "ArrowUp") &&
      items.length
    ) {
      event.preventDefault();
      setOpen(true);
      setActive((old) =>
        event.key === "ArrowDown"
          ? (old + 1) % items.length
          : old <= 0
            ? items.length - 1
            : old - 1,
      );
    } else if (event.key === "Enter" && expanded) {
      event.preventDefault();
      select(items[Math.max(active, 0)]);
    }
  };
  const note = configLoading
    ? "Проверяем доступность подсказок…"
    : !enabled
      ? "Подсказки сейчас недоступны. Введите адрес вручную и при необходимости уточните точку на карте."
      : error
        ? "Не удалось получить подсказки. Можно продолжить с ручным адресом."
        : busy
          ? "Ищем адреса в Казахстане…"
          : searched && !items.length && focused
            ? "Адрес не найден. Добавьте город и номер дома или введите адрес вручную."
            : "Начните с города, затем укажите улицу и дом. Можно вводить на русском или казахском.";
  return (
    <div className="address-search">
      <label className="field" htmlFor={id}>
        <span>{label}</span>
        <input
          id={id}
          name="address"
          type="text"
          autoComplete="street-address"
          value={value}
          required={required}
          minLength={required ? 5 : undefined}
          maxLength={350}
          disabled={disabled}
          placeholder="Например, Алматы, Абая, 10"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={expanded}
          aria-controls={`${id}-list`}
          aria-activedescendant={
            expanded && active >= 0 ? `${id}-option-${active}` : undefined
          }
          aria-describedby={`${id}-note${fieldError ? ` ${id}-error` : ""}`}
          aria-invalid={Boolean(fieldError)}
          aria-busy={busy}
          onChange={(event) => {
            selectedValue.current = null;
            setOpen(true);
            onChange(event.target.value);
          }}
          onFocus={() => {
            setFocused(true);
            setOpen(true);
          }}
          onBlur={() => {
            setFocused(false);
            setOpen(false);
          }}
          onKeyDown={keydown}
        />
        {fieldError && (
          <small className="error-text" id={`${id}-error`}>
            {fieldError}
          </small>
        )}
      </label>
      {expanded && (
        <ul
          id={`${id}-list`}
          className="address-options"
          role="listbox"
          aria-label="Адреса в Казахстане"
        >
          {items.map((item, index) => (
            <li
              id={`${id}-option-${index}`}
              key={`${item.lat}|${item.lon}|${item.label}`}
              role="option"
              aria-selected={active === index}
              className={active === index ? "active" : ""}
              onMouseDown={(event) => {
                event.preventDefault();
                select(item);
              }}
            >
              <span>{item.label}</span>
              {item.city && <small>{item.city} · Казахстан</small>}
            </li>
          ))}
        </ul>
      )}
      <p
        id={`${id}-note`}
        className="form-note address-search-note"
        role="status"
      >
        {note}
      </p>
      {enabled && (
        <p className="address-attribution">
          Поиск адресов:{" "}
          <a
            href="https://www.geoapify.com/"
            target="_blank"
            rel="noopener noreferrer"
          >
            Geoapify
          </a>{" "}
          · © OpenStreetMap contributors
        </p>
      )}
    </div>
  );
}

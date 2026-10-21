import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { api, ApiError, json, messageOf } from "./api";
import { ErrorNotice, Loading, ProductImage } from "./components";
import { clearSubmission, money } from "./lib";
import type { RepeatPreview, RepeatResult } from "./purchaseTypes";
import { operationKey } from "./purchaseTypes";
import { useStore } from "./StoreContext";
import {
  readRepeatOperation,
  saveRepeatOperation,
  clearRepeatOperation,
} from "./repeatOperation";
import type { PendingRepeat } from "./repeatOperation";

const statusLabel = {
  available: "Можно добавить",
  reduced: "Количество уменьшено",
  out_of_stock: "Закончился",
  missing: "Больше не продаётся",
};

export default function RepeatOrder({
  orderId,
  compact = false,
}: {
  orderId: number;
  compact?: boolean;
}) {
  const { user, refreshCart } = useStore();
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const owner = useRef(user?.id);
  owner.current = user?.id;
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<RepeatPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const key = useRef<string | null>(null);
  const pending = useRef<PendingRepeat | null>(null);
  const [operationMemoryOnly, setOperationMemoryOnly] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);
  useEffect(() => {
    request.current?.abort();
    setOpen(false);
    setPreview(null);
    setUncertain(false);
    key.current = null;
    pending.current = null;
  }, [user?.id, orderId]);
  const load = async () => {
    const expected = user?.id;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError("");
    try {
      const next = await api<RepeatPreview>(
        `/orders/${orderId}/repeat-preview`,
        { signal: controller.signal },
      );
      if (owner.current !== expected || controller.signal.aborted) return;
      const saved = expected ? readRepeatOperation(expected, orderId) : null;
      pending.current = saved;
      setPreview(next);
      key.current = saved?.operation_key || operationKey();
      setUncertain(Boolean(saved));
    } catch (problem) {
      if (!controller.signal.aborted && owner.current === expected)
        setError(messageOf(problem));
    } finally {
      if (!controller.signal.aborted && owner.current === expected)
        setBusy(false);
    }
  };
  const close = () => {
    if (busy) return;
    setOpen(false);
    request.current?.abort();
    requestAnimationFrame(() => trigger.current?.focus());
  };
  const confirm = async () => {
    if ((!preview?.can_repeat && !pending.current) || busy || !preview) return;
    const expected = user?.id;
    setBusy(true);
    setError("");
    try {
      key.current ||= operationKey();
      const operation = pending.current || {
        owner_id: expected!,
        order_id: orderId,
        fingerprint: preview.fingerprint,
        operation_key: key.current,
      };
      pending.current = operation;
      setOperationMemoryOnly(!saveRepeatOperation(operation));
      await api<RepeatResult>(`/orders/${orderId}/repeat`, {
        method: "POST",
        body: json({
          fingerprint: operation.fingerprint,
          operation_key: operation.operation_key,
          expected_user_id: operation.owner_id,
        }),
      });
      if (owner.current !== expected) return;
      try {
        clearSubmission();
      } catch {
        /* Optional checkout cache. */
      }
      clearRepeatOperation(expected!, orderId);
      pending.current = null;
      setDone(true);
      setUncertain(false);
      await refreshCart().catch((problem) =>
        setError(
          `Товары добавлены. Не удалось обновить счётчик корзины: ${messageOf(problem)}`,
        ),
      );
    } catch (problem) {
      if (owner.current !== expected) return;
      if (problem instanceof ApiError && problem.status === 409) {
        clearRepeatOperation(expected!, orderId);
        pending.current = null;
        await load();
        setError(
          "Цены, наличие или корзина изменились. Предпросмотр обновлён; проверьте его и подтвердите ещё раз.",
        );
      } else {
        setUncertain(true);
        setError(
          `${messageOf(problem)} Повторите подтверждение: тот же ключ не даст добавить товары дважды.`,
        );
      }
    } finally {
      if (owner.current === expected) setBusy(false);
    }
  };
  return (
    <>
      <button
        ref={trigger}
        type="button"
        className={
          compact ? "text-button repeat-order-trigger" : "button outline"
        }
        onClick={() => {
          setDone(false);
          setOpen(true);
          if (!uncertain) void load();
        }}
        aria-haspopup="dialog"
      >
        Повторить заказ
      </button>
      <dialog
        ref={dialog}
        className="repeat-order-dialog"
        aria-labelledby={`repeat-order-title-${orderId}`}
        onCancel={(event) => {
          event.preventDefault();
          close();
        }}
        onClose={() => {
          setOpen(false);
          trigger.current?.focus();
        }}
      >
        <div className="purchase-section-heading">
          <div>
            <p className="eyebrow">Повторная покупка</p>
            <h2 id={`repeat-order-title-${orderId}`}>
              Повторить заказ №{orderId}
            </h2>
          </div>
          <button
            type="button"
            className="icon-button"
            disabled={busy}
            aria-label="Закрыть повтор заказа"
            onClick={close}
          >
            ×
          </button>
        </div>
        {done ? (
          <div className="repeat-order-success" role="status">
            <h3>Доступные товары добавлены в корзину</h3>
            <ErrorNotice message={error} />
            <p>
              Покупка ещё не оформлена. Проверьте корзину и выберите способ
              получения.
            </p>
            <Link className="button" to="/cart" onClick={close}>
              Перейти в корзину
            </Link>
          </div>
        ) : (
          <>
            <p>
              Добавим товары к существующей корзине по сегодняшним ценам.
              Историческая цена остаётся только для сравнения.
            </p>
            <ErrorNotice
              message={error}
              retry={!preview && !busy ? () => void load() : undefined}
            />
            {busy && !preview ? (
              <Loading text="Проверяем цены и наличие…" />
            ) : (
              preview && (
                <>
                  <div className="repeat-order-items">
                    {preview.items.map((item) => (
                      <article
                        key={item.variant_id}
                        className="repeat-order-item"
                      >
                        <ProductImage
                          src={item.image_url || undefined}
                          alt={item.product_name}
                          loading="lazy"
                        />
                        <div>
                          <h3>{item.product_name}</h3>
                          <p>{item.label}</p>
                          <span
                            className={`repeat-status repeat-status-${item.status}`}
                          >
                            {statusLabel[item.status]}
                          </span>
                          <p>
                            В прошлом заказе: {item.ordered_quantity} шт. · Уже
                            в корзине: {item.existing_quantity} шт.
                          </p>
                          <strong>Добавим: {item.add_quantity} шт.</strong>
                          {item.changes.length > 0 && (
                            <ul>
                              {item.changes.map((change, index) => (
                                <li key={index}>{change}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                        <div className="repeat-order-price">
                          {item.unit_price !== null ? (
                            <>
                              <strong>{money(item.unit_price)} / шт.</strong>
                              {Number(item.previous_unit_price) !==
                                Number(item.unit_price) && (
                                <small>
                                  Раньше {money(item.previous_unit_price)}
                                </small>
                              )}
                              <span>{money(item.line_total)}</span>
                            </>
                          ) : (
                            <span>Цена недоступна</span>
                          )}
                        </div>
                      </article>
                    ))}
                  </div>
                  <p className="repeat-order-total">
                    К корзине: <strong>{money(preview.subtotal)}</strong>
                  </p>
                  {!preview.can_repeat && (
                    <p className="form-note">
                      Сейчас нет доступного количества для повтора. Товары в
                      вашей корзине остаются без изменений.
                    </p>
                  )}
                  <button
                    type="button"
                    className="button"
                    disabled={busy || (!preview.can_repeat && !uncertain)}
                    onClick={() => void confirm()}
                  >
                    {busy
                      ? "Добавляем…"
                      : uncertain
                        ? "Проверить повторное добавление"
                        : "Подтвердить и добавить в корзину"}
                  </button>
                </>
              )
            )}
          </>
        )}
        <p className="form-note">
          {uncertain
            ? "Предыдущий ответ не подтверждён. Проверим результат той же операции, даже если корзина после этого изменилась."
            : "Оплата и новый заказ здесь не создаются."}
        </p>
        {operationMemoryOnly && uncertain && (
          <p className="form-note" role="status">
            Браузер не разрешил сохранить ключ повтора. Не обновляйте страницу,
            пока не проверим результат.
          </p>
        )}
      </dialog>
    </>
  );
}

import { useEffect, useRef, useState } from "react";
import { api, json, messageOf } from "./api";
import { ErrorNotice } from "./components";

export function ReviewReportForm({
  productId,
  reviewId,
}: {
  productId: number;
  reviewId: number;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("spam");
  const [details, setDetails] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const field = useRef<HTMLSelectElement>(null);
  useEffect(() => {
    if (open) field.current?.focus();
  }, [open]);
  const close = () => {
    setOpen(false);
    requestAnimationFrame(() => trigger.current?.focus());
  };
  return (
    <div className="review-report">
      {sent ? (
        <p className="form-note" role="status">
          Жалоба передана администратору. Отзыв остаётся видимым до решения.
        </p>
      ) : (
        <button
          ref={trigger}
          type="button"
          className="text-button"
          aria-expanded={open}
          disabled={busy}
          onClick={() => {
            if (open) close();
            else {
              setError("");
              setOpen(true);
            }
          }}
        >
          Пожаловаться
        </button>
      )}
      {open && (
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (busy) return;
            setBusy(true);
            setError("");
            try {
              await api(`/products/${productId}/reviews/${reviewId}/reports`, {
                method: "POST",
                body: json({ reason, details: details.trim() }),
              });
              setSent(true);
              close();
            } catch (problem) {
              setError(messageOf(problem));
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="field">
            <span>Причина жалобы</span>
            <select
              aria-label="Причина жалобы"
              ref={field}
              disabled={busy}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            >
              <option value="spam">Спам или реклама</option>
              <option value="abuse">Оскорбления</option>
              <option value="irrelevant">Не относится к товару</option>
              <option value="other">Другая причина</option>
            </select>
          </label>
          <label className="field">
            <span>Подробности (необязательно)</span>
            <textarea
              rows={3}
              maxLength={500}
              disabled={busy}
              value={details}
              onChange={(event) => setDetails(event.target.value)}
            />
          </label>
          <ErrorNotice message={error} />
          <div className="button-row">
            <button className="button" disabled={busy}>
              {busy ? "Отправляем…" : "Отправить жалобу"}
            </button>
            <button
              type="button"
              className="button outline"
              disabled={busy}
              onClick={close}
            >
              Отмена
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

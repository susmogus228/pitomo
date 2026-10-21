import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { api, json, messageOf } from "./api";
import { ErrorNotice, Loading, PageTitle } from "./components";
import { ExportControls } from "./ExportControls";
import { useStore } from "./StoreContext";
import { useResource } from "./useResource";
import { adminPage } from "./adminFilters";

interface AdminReviewItem {
  id: number;
  review_id?: number;
  product_id: number;
  product_name: string;
  author_name: string;
  rating: number;
  body: string;
  created_at: string;
  is_hidden: boolean;
  is_deleted?: boolean;
  is_edited?: boolean;
  has_official_reply?: boolean;
  replies_count?: number;
  reason?: string;
  details?: string;
  status?: string;
}
interface ReviewQueue {
  items: AdminReviewItem[];
  total: number;
  limit: number;
  offset: number;
}
type Action = "hide" | "restore" | "dismiss_reports";
const actionNames: Record<Action, string> = {
  hide: "Скрыть отзыв",
  restore: "Вернуть отзыв на сайт",
  dismiss_reports: "Отклонить жалобы",
};
const reportReasons: Record<string, string> = {
  spam: "Спам или реклама",
  abuse: "Оскорбления",
  irrelevant: "Не относится к товару",
  other: "Другая причина",
};
const time = (value: string) => new Date(value).toLocaleString("ru-RU");

function History({ reviewId }: { reviewId: number }) {
  const { user } = useStore();
  const [open, setOpen] = useState(false);
  const [limit, setLimit] = useState(20);
  const history = useResource<{
    items: {
      id: number;
      action: Action;
      reason: string;
      admin_id: number | null;
      created_at: string;
    }[];
    total: number;
  }>(open ? `/admin/reviews/${reviewId}/moderation?limit=${limit}` : null, {
    scope: user?.id,
  });
  return (
    <div className="review-moderation-history">
      <button
        type="button"
        className="text-button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        Журнал модерации
      </button>
      {open &&
        (history.loading ? (
          <Loading />
        ) : history.error ? (
          <ErrorNotice message={history.error} retry={history.reload} />
        ) : history.data?.items.length ? (
          <>
            <ol>
              {history.data.items.map((entry) => (
                <li key={entry.id}>
                  <strong>{actionNames[entry.action]}</strong> ·{" "}
                  {time(entry.created_at)} · администратор{" "}
                  {entry.admin_id ?? "удалён"}
                  <p>{entry.reason}</p>
                </li>
              ))}
            </ol>
            {history.data.total > limit && limit < 100 && (
              <button
                type="button"
                className="text-button"
                onClick={() => setLimit(Math.min(100, limit + 20))}
              >
                Показать более ранние действия
              </button>
            )}
          </>
        ) : (
          <p className="form-note">Действий пока нет.</p>
        ))}
    </div>
  );
}

export function AdminReviewModeration() {
  const { user } = useStore();
  const [params, setParams] = useSearchParams();
  const view =
    params.get("view") === "reports"
      ? "reports"
      : params.get("view") === "hidden"
        ? "hidden"
        : "visible";
  const reportStatus = ["pending", "dismissed", "actioned", "all"].includes(
    params.get("report_status") || "",
  )
    ? params.get("report_status")!
    : "pending";
  const onlyUnanswered = params.get("unanswered") === "true";
  const page = adminPage(params);
  const change = (updates: Record<string, string>, resetPage = true) => {
    const next = new URLSearchParams(params);
    if (resetPage) next.delete("page");
    for (const [key, value] of Object.entries(updates))
      if (value) next.set(key, value);
      else next.delete(key);
    setParams(next);
    setAction(null);
    setReplying(null);
    setError("");
    setSuccess("");
  };
  const path =
    view === "reports"
      ? `/admin/review-reports?status=${reportStatus}&limit=20&offset=${(page - 1) * 20}`
      : `/admin/reviews?visibility=${view}&unanswered_only=${onlyUnanswered}&limit=20&offset=${(page - 1) * 20}`;
  const queue = useResource<ReviewQueue>(path, { scope: user?.id });
  const [action, setAction] = useState<{
    id: number;
    rowId: number;
    value: Action;
  } | null>(null);
  const [reason, setReason] = useState("");
  const [replying, setReplying] = useState<number | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const reasonInput = useRef<HTMLTextAreaElement>(null);
  const answerInput = useRef<HTMLTextAreaElement>(null);
  const actionTrigger = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (action) reasonInput.current?.focus();
  }, [action]);
  useEffect(() => {
    if (replying) answerInput.current?.focus();
  }, [replying]);
  const cancel = () => {
    setAction(null);
    setReplying(null);
    setError("");
    requestAnimationFrame(() => actionTrigger.current?.focus());
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!action || busy || !reason.trim()) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await api(`/admin/reviews/${action.id}/moderation`, {
        method: "POST",
        body: json({ action: action.value, reason: reason.trim() }),
      });
      setSuccess("Решение сохранено в журнале модерации.");
      cancel();
      queue.reload();
    } catch (problem) {
      setError(messageOf(problem));
    } finally {
      setBusy(false);
    }
  };
  const reply = async (event: FormEvent, item: AdminReviewItem) => {
    event.preventDefault();
    if (busy || !answer.trim()) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await api(
        `/products/${item.product_id}/reviews/${item.review_id ?? item.id}/replies`,
        { method: "POST", body: json({ body: answer.trim(), official: true }) },
      );
      setSuccess("Официальный ответ опубликован.");
      cancel();
      queue.reload();
    } catch (problem) {
      setError(messageOf(problem));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section>
      <PageTitle
        eyebrow="Обратная связь"
        subtitle="Жалоба сама по себе не скрывает отзыв. Решение принимает администратор с указанием причины."
      >
        Отзывы и модерация
      </PageTitle>
      <div className="admin-review-tabs" aria-label="Разделы отзывов">
        {[
          ["visible", "Опубликованные"],
          ["hidden", "Скрытые"],
          ["reports", "Жалобы"],
        ].map(([value, label]) => (
          <button
            type="button"
            key={value}
            className={`button ${view === value ? "" : "outline"}`}
            aria-pressed={view === value}
            disabled={busy}
            onClick={() => change({ view: value, unanswered: "" })}
          >
            {label}
          </button>
        ))}
      </div>
      {view === "reports" ? (
        <label className="field">
          <span>Состояние жалоб</span>
          <select
            aria-label="Состояние жалоб"
            disabled={busy}
            value={reportStatus}
            onChange={(event) => change({ report_status: event.target.value })}
          >
            <option value="pending">Ждут решения</option>
            <option value="dismissed">Отклонённые</option>
            <option value="actioned">Отзыв скрыт по решению</option>
            <option value="all">Все жалобы</option>
          </select>
        </label>
      ) : (
        <>
          <label className="admin-checkbox">
            <input
              type="checkbox"
              disabled={busy}
              checked={onlyUnanswered}
              onChange={(event) =>
                change({ unanswered: event.target.checked ? "true" : "" })
              }
            />{" "}
            Только без ответа магазина
          </label>
          <ExportControls
            dataset="reviews"
            filters={{ visibility: view, unanswered_only: onlyUnanswered }}
          />
        </>
      )}
      {success && (
        <p className="success-text" role="status">
          {success}
        </p>
      )}
      {queue.error && (
        <ErrorNotice message={queue.error} retry={queue.reload} />
      )}
      {queue.loading && !queue.data ? (
        <Loading />
      ) : (
        queue.data && (
          <>
            <p className="form-note">Найдено: {queue.data.total}</p>
            <div className="admin-review-list" aria-busy={queue.refreshing}>
              {queue.data.items.map((item) => {
                const id = item.review_id ?? item.id;
                return (
                  <article key={`${item.id}-${view}`} className="admin-review">
                    <div className="admin-review-meta">
                      <strong>{item.author_name}</strong>
                      <span>★ {item.rating} / 5</span>
                      <time dateTime={item.created_at}>
                        {time(item.created_at)}
                      </time>
                      {item.is_edited && <span>Изменён</span>}
                    </div>
                    <h2>
                      <Link to={`/product/${item.product_id}#reviews`}>
                        {item.product_name} ↗
                      </Link>
                    </h2>
                    <p>{item.body || "Автор удалил текст"}</p>
                    {item.reason && (
                      <div className="admin-report-details">
                        <strong>
                          {reportReasons[item.reason] || item.reason}
                        </strong>
                        <p>
                          {item.details || "Без дополнительных подробностей"}
                        </p>
                        <small>
                          Состояние:{" "}
                          {item.status === "pending"
                            ? "ждёт решения"
                            : item.status === "actioned"
                              ? "приняты меры"
                              : "отклонена"}
                        </small>
                      </div>
                    )}
                    <p className="form-note">
                      {item.is_deleted
                        ? "Автор удалил отзыв"
                        : item.is_hidden
                          ? "Скрыт с сайта и из рейтинга"
                          : "Опубликован на сайте"}
                    </p>
                    <div className="button-row">
                      {(!item.is_deleted
                        ? [
                            item.is_hidden ? "restore" : "hide",
                            ...(view === "reports" && item.status === "pending"
                              ? ["dismiss_reports"]
                              : []),
                          ]
                        : item.status === "pending"
                          ? ["dismiss_reports"]
                          : []
                      ).map((value) => (
                        <button
                          type="button"
                          className="button outline"
                          key={value}
                          disabled={busy}
                          onClick={(event) => {
                            actionTrigger.current = event.currentTarget;
                            setAction({
                              id,
                              rowId: item.id,
                              value: value as Action,
                            });
                            setReason("");
                            setReplying(null);
                            setError("");
                          }}
                        >
                          {actionNames[value as Action]}
                        </button>
                      ))}
                      {!item.is_hidden &&
                        !item.is_deleted &&
                        view !== "reports" &&
                        !item.has_official_reply && (
                          <button
                            type="button"
                            className="text-button"
                            disabled={busy}
                            onClick={(event) => {
                              actionTrigger.current = event.currentTarget;
                              setReplying(id);
                              setAnswer("");
                              setAction(null);
                              setError("");
                            }}
                          >
                            Ответить от магазина
                          </button>
                        )}
                    </div>
                    {action?.rowId === item.id && (
                      <form
                        className="review-moderation-form"
                        onSubmit={submit}
                      >
                        <strong>{actionNames[action.value]}</strong>
                        <label className="field">
                          <span>Причина решения</span>
                          <textarea
                            ref={reasonInput}
                            required
                            maxLength={500}
                            rows={3}
                            value={reason}
                            disabled={busy}
                            onChange={(event) => setReason(event.target.value)}
                          />
                        </label>
                        <ErrorNotice message={error} />
                        <div className="button-row">
                          <button
                            className="button"
                            disabled={busy || !reason.trim()}
                          >
                            {busy ? "Сохраняем…" : "Подтвердить решение"}
                          </button>
                          <button
                            type="button"
                            className="button outline"
                            disabled={busy}
                            onClick={cancel}
                          >
                            Отмена
                          </button>
                        </div>
                      </form>
                    )}
                    {replying === id && (
                      <form
                        className="admin-answer-form"
                        onSubmit={(event) => void reply(event, item)}
                      >
                        <label className="field">
                          <span>Официальный ответ</span>
                          <textarea
                            ref={answerInput}
                            required
                            minLength={1}
                            maxLength={2000}
                            rows={3}
                            value={answer}
                            disabled={busy}
                            onChange={(event) => setAnswer(event.target.value)}
                          />
                        </label>
                        <ErrorNotice message={error} />
                        <div className="button-row">
                          <button
                            className="button"
                            disabled={busy || !answer.trim()}
                          >
                            Опубликовать ответ
                          </button>
                          <button
                            type="button"
                            className="button outline"
                            disabled={busy}
                            onClick={cancel}
                          >
                            Отмена
                          </button>
                        </div>
                      </form>
                    )}
                    <History
                      key={`${id}-${item.is_hidden}-${queue.data?.total}`}
                      reviewId={id}
                    />
                  </article>
                );
              })}
            </div>
            {!queue.data.items.length && (
              <p className="form-note">
                По выбранным условиям ничего не найдено.
              </p>
            )}
            {(page > 1 || queue.data.total > 20) && (
              <nav className="pagination" aria-label="Страницы модерации">
                <button
                  type="button"
                  className="button outline"
                  disabled={page <= 1 || busy || queue.loading}
                  onClick={() => change({ page: String(page - 1) }, false)}
                >
                  Назад
                </button>
                <span>
                  {page} / {Math.max(1, Math.ceil(queue.data.total / 20))}
                </span>
                <button
                  type="button"
                  className="button outline"
                  disabled={
                    page * 20 >= queue.data.total || busy || queue.loading
                  }
                  onClick={() => change({ page: String(page + 1) }, false)}
                >
                  Дальше
                </button>
              </nav>
            )}
          </>
        )
      )}
    </section>
  );
}

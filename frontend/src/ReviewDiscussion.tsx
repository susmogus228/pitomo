import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, json, messageOf } from "./api";
import { ErrorNotice } from "./components";
import { dateLabel } from "./lib";
import { uploadReviewPhotoFiles } from "./reviewPhotoUploads";
import { useStore } from "./StoreContext";
import type { Review, ReviewPhoto, ReviewReply } from "./types";
import { ReviewReportForm } from "./ReviewReportForm";

export function selectedPhotos(files: FileList | null): File[] {
  return Array.from(files || []);
}
export function validatePhotos(files: File[], existingCount = 0): string {
  if (files.length + existingCount > 3)
    return "Можно прикрепить не более 3 фото.";
  if (
    files.some(
      (file) => !["image/jpeg", "image/png", "image/webp"].includes(file.type),
    )
  )
    return "Выберите JPG, PNG или WebP.";
  if (files.some((file) => !file.size || file.size > 5 * 1024 * 1024))
    return "Каждое фото должно быть непустым и не больше 5 МБ.";
  return "";
}
export async function uploadPhotos(path: string, files: File[]) {
  return uploadReviewPhotoFiles(files, (file) => {
    const body = new FormData();
    body.set("file", file);
    return api(path, { method: "POST", body });
  });
}

export function useReviewPhotoRecovery(
  onChanged: () => void,
  scope?: number,
  onRecovered?: () => void,
) {
  const { user } = useStore();
  const [pending, setPending] = useState<{
    path: string;
    files: File[];
    note: string;
    error: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const retrying = useRef(false);
  const retryButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    setPending(null);
  }, [user?.id, scope]);
  useEffect(() => {
    if (pending) retryButton.current?.focus();
  }, [pending]);
  const upload = async (path: string, files: File[], note: string) => {
    const result = await uploadPhotos(path, files);
    setPending(
      result.failed.length
        ? { path, files: result.failed, note, error: result.errors.join(" ") }
        : null,
    );
    return result;
  };
  const retry = async () => {
    if (!pending || retrying.current) return;
    retrying.current = true;
    setBusy(true);
    try {
      const result = await upload(pending.path, pending.files, pending.note);
      onChanged();
      if (!result.failed.length) onRecovered?.();
    } finally {
      retrying.current = false;
      setBusy(false);
    }
  };
  const notice = pending && (
    <div
      className="review-photo-recovery"
      role="alert"
      style={{ overflowWrap: "anywhere" }}
    >
      <p>
        {pending.note} Не загрузилось фото: {pending.files.length}.{" "}
        {pending.error}
      </p>
      <p className="form-note">
        Повторим только неудачные загрузки. Файлы хранятся в памяти вкладки до
        обновления страницы.
      </p>
      <ul>
        {pending.files.map((file, index) => (
          <li key={index}>{file.name}</li>
        ))}
      </ul>
      <div className="button-row">
        <button
          type="button"
          ref={retryButton}
          className="button outline"
          disabled={busy}
          onClick={() => void retry()}
        >
          {busy ? "Загружаем…" : "Повторить загрузку фото"}
        </button>
        <button
          type="button"
          className="text-button"
          disabled={busy}
          onClick={() => {
            setPending(null);
            onRecovered?.();
          }}
        >
          Продолжить без этих фото
        </button>
      </div>
    </div>
  );
  return { upload, notice, busy, pending: Boolean(pending) };
}

function LengthHint({
  id,
  body,
  min,
}: {
  id: string;
  body: string;
  min: number;
}) {
  return (
    <span className="form-note" id={id}>
      От {min} до 2000 символов. Сейчас: {body.trim().length} / 2000.
    </span>
  );
}
function Photos({
  photos,
  owner,
  busy,
  onDelete,
}: {
  photos: ReviewPhoto[];
  owner: boolean;
  busy: boolean;
  onDelete: (id: number) => Promise<void>;
}) {
  if (!photos?.length) return null;
  return (
    <div className="review-photos">
      {photos.map((photo, index) => (
        <div className="review-photo" key={photo.id}>
          <a
            href={photo.url}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Открыть фото ${index + 1}`}
          >
            <img
              src={photo.url}
              loading="lazy"
              alt={`Фото ${index + 1} к отзыву`}
            />
          </a>
          {owner && (
            <button
              type="button"
              className="review-photo-remove"
              aria-label={`Удалить фото ${index + 1}`}
              disabled={busy}
              onClick={() => void onDelete(photo.id)}
            >
              ×
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
function restoreFocus(element: HTMLElement | null) {
  window.requestAnimationFrame(() => {
    if (element?.isConnected) element.focus();
  });
}

function ReviewReplyCard({
  productId,
  reviewId,
  reply,
  replyingTo,
  onChanged,
  onReply,
  replyDisabled,
}: {
  productId: number;
  reviewId: number;
  reply: ReviewReply;
  replyingTo?: string;
  onChanged: () => void;
  onReply: (parent: ReviewReply, trigger: HTMLButtonElement) => void;
  replyDisabled: boolean;
}) {
  const { user } = useStore();
  const owner = Boolean(
    user && user.id === reply.author_id && !reply.is_deleted,
  );
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState(reply.body);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const textarea = useRef<HTMLTextAreaElement>(null);
  const editButton = useRef<HTMLButtonElement>(null);
  const recovery = useReviewPhotoRecovery(onChanged, reply.id, () =>
    restoreFocus(editButton.current),
  );
  const locked = busy || recovery.busy;
  const base = `/products/${productId}/reviews/${reviewId}/replies/${reply.id}`;
  const hintId = `reply-${reply.id}-length`;
  useEffect(() => {
    if (editing) textarea.current?.focus();
  }, [editing]);
  const close = () => {
    setEditing(false);
    setFiles([]);
    setError("");
    restoreFocus(editButton.current);
  };
  const mutate = async (action: () => Promise<unknown>) => {
    if (locked) return;
    setBusy(true);
    setError("");
    try {
      await action();
      onChanged();
    } catch (problem) {
      setError(messageOf(problem));
    } finally {
      setBusy(false);
    }
  };
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const issue = validatePhotos(files, reply.photos?.length || 0);
    if (issue) {
      setError(issue);
      return;
    }
    await mutate(async () => {
      await api(base, { method: "PATCH", body: json({ body: body.trim() }) });
      await recovery.upload(`${base}/photos`, files, "Текст ответа сохранён.");
      close();
    });
  };
  return (
    <article
      className={`review-reply ${reply.is_official ? "review-reply-official" : ""} ${reply.parent_reply_id ? "review-reply-nested" : ""}`}
      aria-busy={locked}
    >
      <div className="review-reply-head">
        <strong>{reply.author_name}</strong>
        {reply.is_official && (
          <span className="review-official">
            Ответ магазина{reply.is_pinned ? " · закреплён" : ""}
          </span>
        )}
        <time dateTime={reply.created_at}>{dateLabel(reply.created_at)}</time>
        {reply.is_edited && (
          <span className="review-edited">
            Изменён{reply.edited_at ? ` ${dateLabel(reply.edited_at)}` : ""}
          </span>
        )}
      </div>
      {replyingTo && (
        <span className="review-reply-target">
          В ответ пользователю {replyingTo}
        </span>
      )}
      {reply.is_deleted ? (
        <p className="review-deleted">Ответ удалён</p>
      ) : editing ? (
        <form
          className="review-inline-form"
          onSubmit={(event) => void save(event)}
        >
          <label className="field">
            <span>Изменить ответ</span>
            <textarea
              ref={textarea}
              required
              minLength={2}
              maxLength={2000}
              rows={3}
              value={body}
              disabled={locked}
              aria-describedby={hintId}
              onChange={(event) => setBody(event.target.value)}
            />
            <LengthHint id={hintId} body={body} min={2} />
          </label>
          <label className="field">
            <span>Добавить фото</span>
            <input
              type="file"
              disabled={locked}
              accept="image/jpeg,image/png,image/webp"
              multiple
              onChange={(event) => setFiles(selectedPhotos(event.target.files))}
            />
          </label>
          <ErrorNotice message={error} />
          <div className="button-row">
            <button
              className="button"
              disabled={locked || body.trim().length < 2}
            >
              {busy ? "Сохраняем…" : "Сохранить"}
            </button>
            <button
              type="button"
              className="button outline"
              disabled={locked}
              onClick={close}
            >
              Отмена
            </button>
          </div>
        </form>
      ) : (
        <p>{reply.body}</p>
      )}
      {!reply.is_deleted && (
        <Photos
          photos={reply.photos || []}
          owner={owner}
          busy={locked}
          onDelete={async (id) => {
            await mutate(() =>
              api<void>(`${base}/photos/${id}`, { method: "DELETE" }),
            );
          }}
        />
      )}
      {!reply.is_deleted && (
        <div className="review-actions">
          {user && !reply.parent_reply_id && (
            <button
              type="button"
              className="text-button"
              disabled={locked || editing || recovery.pending || replyDisabled}
              onClick={(event) => onReply(reply, event.currentTarget)}
            >
              Ответить
            </button>
          )}
          {owner && (
            <>
              <button
                type="button"
                ref={editButton}
                className="text-button"
                disabled={locked || recovery.pending || editing}
                onClick={() => {
                  setEditing(true);
                  setBody(reply.body);
                }}
              >
                Редактировать
              </button>
              <button
                type="button"
                className="text-button danger-text"
                disabled={locked}
                onClick={() => {
                  if (window.confirm("Удалить ваш ответ?"))
                    void mutate(() => api<void>(base, { method: "DELETE" }));
                }}
              >
                Удалить
              </button>
            </>
          )}
        </div>
      )}
      {!editing && <ErrorNotice message={error} />}
      {recovery.notice}
    </article>
  );
}

export function ReviewDiscussion({
  productId,
  review,
  onChanged,
  onDeleted,
}: {
  productId: number;
  review: Review;
  onChanged: () => void;
  onDeleted?: () => void;
}) {
  const { user } = useStore();
  const owner = Boolean(user && user.id === review.author_id);
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState(review.body);
  const [rating, setRating] = useState(review.rating);
  const [files, setFiles] = useState<File[]>([]);
  const [replyTarget, setReplyTarget] = useState<
    ReviewReply | null | undefined
  >(undefined);
  const [replyBody, setReplyBody] = useState("");
  const [replyFiles, setReplyFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const editTextarea = useRef<HTMLTextAreaElement>(null);
  const replyTextarea = useRef<HTMLTextAreaElement>(null);
  const editButton = useRef<HTMLButtonElement>(null);
  const replyTrigger = useRef<HTMLButtonElement | null>(null);
  const recovery = useReviewPhotoRecovery(onChanged, review.id, () =>
    restoreFocus(editButton.current || replyTrigger.current),
  );
  const locked = busy || recovery.busy;
  const base = `/products/${productId}/reviews/${review.id}`;
  const editHint = `review-${review.id}-edit-length`;
  const replyHint = `review-${review.id}-reply-length`;
  useEffect(() => {
    if (editing) editTextarea.current?.focus();
  }, [editing]);
  useEffect(() => {
    if (replyTarget !== undefined) replyTextarea.current?.focus();
  }, [replyTarget]);
  const closeEdit = () => {
    setEditing(false);
    setFiles([]);
    setError("");
    restoreFocus(editButton.current);
  };
  const closeReply = () => {
    setReplyTarget(undefined);
    setReplyBody("");
    setReplyFiles([]);
    setError("");
    restoreFocus(replyTrigger.current);
  };
  const openReply = (
    target: ReviewReply | null,
    trigger: HTMLButtonElement,
  ) => {
    replyTrigger.current = trigger;
    setReplyTarget(target);
    setReplyBody("");
    setError("");
  };
  const mutate = async (action: () => Promise<unknown>) => {
    if (locked) return;
    setBusy(true);
    setError("");
    try {
      await action();
      onChanged();
    } catch (problem) {
      setError(messageOf(problem));
    } finally {
      setBusy(false);
    }
  };
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const issue = validatePhotos(files, review.photos?.length || 0);
    if (issue) {
      setError(issue);
      return;
    }
    await mutate(async () => {
      await api(base, {
        method: "PATCH",
        body: json({ rating, body: body.trim() }),
      });
      await recovery.upload(`${base}/photos`, files, "Отзыв сохранён.");
      closeEdit();
    });
  };
  const submitReply = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const issue = validatePhotos(replyFiles);
    if (issue) {
      setError(issue);
      return;
    }
    await mutate(async () => {
      const created = await api<ReviewReply>(`${base}/replies`, {
        method: "POST",
        body: json({
          body: replyBody.trim(),
          ...(replyTarget ? { parent_reply_id: replyTarget.id } : {}),
          ...(user?.role === "admin" ? { official: true } : {}),
        }),
      });
      await recovery.upload(
        `${base}/replies/${created.id}/photos`,
        replyFiles,
        "Ответ опубликован.",
      );
      closeReply();
    });
  };
  const orderedReplies = [...(review.replies || [])].sort(
    (a, b) =>
      Number(b.is_pinned) - Number(a.is_pinned) ||
      Date.parse(a.created_at) - Date.parse(b.created_at),
  );
  const topLevelReplies = orderedReplies.filter(
    (reply) =>
      !reply.parent_reply_id ||
      !orderedReplies.some((parent) => parent.id === reply.parent_reply_id),
  );
  return (
    <article className="review-card" aria-busy={locked}>
      <div className="review-card-head">
        <strong>{review.author_name}</strong>
        <span aria-label={`${review.rating} из 5`}>
          {"★".repeat(review.rating)}
          {"☆".repeat(5 - review.rating)}
        </span>
        <time dateTime={review.created_at}>{dateLabel(review.created_at)}</time>
        {review.verified_purchase && (
          <span className="review-verified">Покупка подтверждена</span>
        )}
        {review.is_edited && (
          <span className="review-edited">
            Изменён{review.edited_at ? ` ${dateLabel(review.edited_at)}` : ""}
          </span>
        )}
      </div>
      {editing ? (
        <form
          className="review-inline-form"
          onSubmit={(event) => void save(event)}
        >
          <label className="field">
            <span>Оценка</span>
            <select
              value={rating}
              disabled={locked}
              onChange={(event) => setRating(Number(event.target.value))}
            >
              {[5, 4, 3, 2, 1].map((value) => (
                <option key={value} value={value}>
                  {value} из 5
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Ваш отзыв</span>
            <textarea
              ref={editTextarea}
              required
              minLength={10}
              maxLength={2000}
              rows={4}
              disabled={locked}
              value={body}
              aria-describedby={editHint}
              onChange={(event) => setBody(event.target.value)}
            />
            <LengthHint id={editHint} body={body} min={10} />
          </label>
          <label className="field">
            <span>Добавить фото</span>
            <input
              type="file"
              disabled={locked}
              multiple
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) => setFiles(selectedPhotos(event.target.files))}
            />
          </label>
          <ErrorNotice message={error} />
          <div className="button-row">
            <button
              className="button"
              disabled={locked || body.trim().length < 10}
            >
              {busy ? "Сохраняем…" : "Сохранить"}
            </button>
            <button
              type="button"
              className="button outline"
              disabled={locked}
              onClick={closeEdit}
            >
              Отмена
            </button>
          </div>
        </form>
      ) : (
        <p>{review.body}</p>
      )}
      <Photos
        photos={review.photos || []}
        owner={owner}
        busy={locked}
        onDelete={async (id) => {
          await mutate(() =>
            api<void>(`${base}/photos/${id}`, { method: "DELETE" }),
          );
        }}
      />
      <div className="review-actions">
        {user &&
          !(
            user.role === "admin" &&
            review.replies?.some((reply) => reply.is_official)
          ) && (
            <button
              type="button"
              className="text-button"
              disabled={
                locked ||
                recovery.pending ||
                editing ||
                replyTarget !== undefined
              }
              onClick={(event) => openReply(null, event.currentTarget)}
            >
              {user.role === "admin" ? "Ответить от магазина" : "Ответить"}
            </button>
          )}
        {owner && (
          <>
            <button
              type="button"
              ref={editButton}
              className="text-button"
              disabled={
                locked ||
                recovery.pending ||
                editing ||
                replyTarget !== undefined
              }
              onClick={() => {
                setEditing(true);
                setBody(review.body);
                setRating(review.rating);
              }}
            >
              Редактировать
            </button>
            <button
              type="button"
              className="text-button danger-text"
              disabled={locked}
              onClick={() => {
                if (window.confirm("Удалить ваш отзыв и ответы к нему?"))
                  void mutate(async () => {
                    await api<void>(base, { method: "DELETE" });
                    onDeleted?.();
                  });
              }}
            >
              Удалить
            </button>
          </>
        )}
      </div>
      {replyTarget !== undefined && (
        <form
          className="review-inline-form review-reply-form"
          onSubmit={(event) => void submitReply(event)}
        >
          <label className="field">
            <span>
              {replyTarget
                ? `Ответ пользователю ${replyTarget.author_name}`
                : user?.role === "admin"
                  ? "Официальный ответ магазина"
                  : "Ваш ответ"}
            </span>
            <textarea
              ref={replyTextarea}
              required
              minLength={2}
              maxLength={2000}
              rows={3}
              disabled={locked}
              value={replyBody}
              aria-describedby={replyHint}
              onChange={(event) => setReplyBody(event.target.value)}
            />
            <LengthHint id={replyHint} body={replyBody} min={2} />
          </label>
          <label className="field">
            <span>Фото (необязательно, до 3)</span>
            <input
              type="file"
              disabled={locked}
              multiple
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) =>
                setReplyFiles(selectedPhotos(event.target.files))
              }
            />
          </label>
          <ErrorNotice message={error} />
          <div className="button-row">
            <button
              className="button"
              disabled={locked || replyBody.trim().length < 2}
            >
              {busy ? "Публикуем…" : "Опубликовать ответ"}
            </button>
            <button
              type="button"
              className="button outline"
              disabled={locked}
              onClick={closeReply}
            >
              Отмена
            </button>
          </div>
        </form>
      )}
      {!editing && replyTarget === undefined && <ErrorNotice message={error} />}
      {recovery.notice}
      {orderedReplies.length > 0 && (
        <section className="review-replies" aria-label="Ответы на отзыв">
          {topLevelReplies.map((reply) => (
            <div className="review-reply-thread" key={reply.id}>
              <ReviewReplyCard
                productId={productId}
                reviewId={review.id}
                reply={reply}
                onChanged={onChanged}
                onReply={openReply}
                replyDisabled={
                  locked ||
                  recovery.pending ||
                  editing ||
                  replyTarget !== undefined
                }
              />
              {orderedReplies
                .filter((child) => child.parent_reply_id === reply.id)
                .map((child) => (
                  <ReviewReplyCard
                    key={child.id}
                    productId={productId}
                    reviewId={review.id}
                    reply={child}
                    replyingTo={reply.author_name}
                    onChanged={onChanged}
                    onReply={openReply}
                    replyDisabled={
                      locked ||
                      recovery.pending ||
                      editing ||
                      replyTarget !== undefined
                    }
                  />
                ))}
            </div>
          ))}
        </section>
      )}
      {user && !owner && !editing && replyTarget === undefined && (
        <ReviewReportForm productId={productId} reviewId={review.id} />
      )}
    </article>
  );
}

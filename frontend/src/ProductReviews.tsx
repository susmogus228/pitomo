import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { api, json, messageOf } from "./api";
import { ErrorNotice, Loading } from "./components";
import { dateLabel } from "./lib";
import {
  ReviewDiscussion,
  selectedPhotos,
  useReviewPhotoRecovery,
  validatePhotos,
} from "./ReviewDiscussion";
import { useStore } from "./StoreContext";
import type { Order, Product, Review, ReviewPage } from "./types";
import { useResource } from "./useResource";
import {
  readReviewFilters,
  reviewApiQuery,
  updateReviewFilters,
} from "./reviewFilters";

export function ProductReviews({ product }: { product: Product }) {
  const { user } = useStore();
  const [params, setParams] = useSearchParams();
  const filters = readReviewFilters(params);
  const page = filters.page;
  const setFilters = (updates: Parameters<typeof updateReviewFilters>[1]) =>
    setParams(updateReviewFilters(params, updates), {
      preventScrollReset: true,
    });
  const setPage = (value: number | ((current: number) => number)) =>
    setFilters({ page: typeof value === "function" ? value(page) : value });
  const [historyOffset, setHistoryOffset] = useState(0);
  const [orders, setOrders] = useState<Order[]>([]);
  const [rating, setRating] = useState(5);
  const [body, setBody] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const [selectedOrder, setSelectedOrder] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const limit = 5;
  const reviews = useResource<ReviewPage>(
    `/products/${product.id}/reviews?${reviewApiQuery(filters)}`,
  );
  const mine = useResource<Review | null>(
    user ? `/products/${product.id}/reviews/mine` : null,
    { scope: user?.id },
  );
  const reload = () => {
    reviews.reload();
    mine.reload();
  };
  const recovery = useReviewPhotoRecovery(reload, product.id);
  const history = useResource<Order[]>(
    user ? `/orders?limit=100&offset=${historyOffset}` : null,
    { scope: user?.id },
  );

  useEffect(() => {
    setOrders([]);
    setHistoryOffset(0);
    setSubmitted(false);
    setSuccess("");
  }, [user?.id, product.id]);

  useEffect(() => {
    if (window.location.hash === "#reviews")
      document.getElementById("reviews")?.scrollIntoView();
  }, [product.id]);

  useEffect(() => {
    if (!user || !history.data) return;
    setOrders((previous) =>
      historyOffset
        ? [
            ...previous,
            ...history.data!.filter(
              (order) => !previous.some((old) => old.id === order.id),
            ),
          ]
        : history.data!,
    );
  }, [history.data, historyOffset, user]);

  const eligible = orders.filter(
    (order) =>
      order.user_id === user?.id &&
      order.received_at &&
      order.items.some((item) => item.product_id === product.id),
  );
  const orderId = eligible.some((order) => order.id === selectedOrder)
    ? selectedOrder
    : eligible[0]?.id;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!orderId || busy) return;
    const photoError = validatePhotos(photos);
    if (photoError) {
      setError(photoError);
      return;
    }
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const created = await api<Review>(`/products/${product.id}/reviews`, {
        method: "POST",
        body: json({ order_id: orderId, rating, body: body.trim() }),
      });
      await recovery.upload(
        `/products/${product.id}/reviews/${created.id}/photos`,
        photos,
        "Отзыв опубликован.",
      );
      setBody("");
      setPhotos([]);
      setPage(1);
      reviews.reload();
      setSuccess("Спасибо! Отзыв опубликован.");
      setSubmitted(true);
    } catch (problem) {
      const message = messageOf(problem);
      if (message.includes("уже оставили отзыв")) {
        setSubmitted(true);
        setSuccess("Вы уже оставили отзыв об этом товаре.");
      } else setError(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      className="reviews-section"
      id="reviews"
      aria-labelledby="reviews-title"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">Опыт покупателей</p>
          <h2 id="reviews-title">Отзывы о товаре</h2>
        </div>
        {reviews.data && (
          <p
            className="review-score"
            aria-label={`Средняя оценка: ${reviews.data.average_rating == null ? "пока нет" : reviews.data.average_rating.toFixed(1)} из 5; отзывов: ${reviews.data.summary_total ?? reviews.data.total}`}
          >
            {reviews.data.average_rating == null
              ? "Пока без оценки"
              : `★ ${reviews.data.average_rating.toFixed(1)} / 5`}{" "}
            <span>· {reviews.data.summary_total ?? reviews.data.total}</span>
          </p>
        )}
      </div>
      <div className="review-trust-controls">
        {reviews.data?.rating_distribution && (
          <div
            className="rating-distribution"
            aria-label="Распределение оценок"
          >
            {[5, 4, 3, 2, 1].map((stars) => {
              const count =
                reviews.data?.rating_distribution?.[String(stars)] || 0;
              const total = reviews.data?.summary_total || 0;
              return (
                <button
                  key={stars}
                  type="button"
                  aria-pressed={filters.rating === String(stars)}
                  onClick={() =>
                    setFilters({
                      rating:
                        filters.rating === String(stars) ? "" : String(stars),
                    })
                  }
                >
                  <span>{stars} ★</span>
                  <span className="rating-bar" aria-hidden="true">
                    <span
                      style={{ width: `${total ? (count / total) * 100 : 0}%` }}
                    />
                  </span>
                  <span>{count}</span>
                </button>
              );
            })}
          </div>
        )}
        <div className="review-filter-fields">
          <label className="field">
            <span>Порядок отзывов</span>
            <select
              aria-label="Порядок отзывов"
              value={filters.sort}
              onChange={(event) =>
                setFilters({ sort: event.target.value as typeof filters.sort })
              }
            >
              <option value="newest">Сначала новые</option>
              <option value="oldest">Сначала ранние</option>
              <option value="rating_desc">С высокой оценкой</option>
              <option value="rating_asc">С низкой оценкой</option>
            </select>
          </label>
          <label className="admin-checkbox">
            <input
              type="checkbox"
              checked={filters.withPhotos}
              onChange={(event) =>
                setFilters({ withPhotos: event.target.checked })
              }
            />{" "}
            Только с фото
          </label>
          {filters.rating && (
            <p className="form-note">Оценка: {filters.rating} из 5</p>
          )}
          {(filters.withPhotos || filters.rating) && (
            <button
              type="button"
              className="text-button"
              onClick={() => setFilters({ withPhotos: false, rating: "" })}
            >
              Сбросить фильтры отзывов
            </button>
          )}
        </div>
      </div>
      {user ? (
        <div className="review-form-wrap">
          {mine.loading && !mine.data ? (
            <Loading text="Проверяем ваш отзыв…" />
          ) : mine.error ? (
            <ErrorNotice message={mine.error} retry={mine.reload} />
          ) : mine.data ? (
            <p
              className={mine.data.is_hidden ? "form-note" : "success-text"}
              role="status"
            >
              {mine.data.is_hidden
                ? "Ваш отзыв скрыт администратором. Редактирование и повторная публикация недоступны до решения модерации."
                : "Вы уже оставили отзыв об этом товаре. Его можно изменить или удалить в списке отзывов."}
            </p>
          ) : submitted ? (
            <p className="success-text" role="status">
              {success}
            </p>
          ) : history.loading && !orders.length ? (
            <Loading text="Проверяем полученные заказы…" />
          ) : history.error ? (
            <ErrorNotice message={history.error} retry={history.reload} />
          ) : eligible.length ? (
            <form
              className="review-form"
              onSubmit={(event) => void submit(event)}
            >
              <h3>Поделитесь впечатлением</h3>
              <p className="form-note">
                Отзыв можно оставить только о товаре из полученного заказа.
              </p>
              {eligible.length > 1 && (
                <label className="field">
                  <span>Заказ</span>
                  <select
                    value={orderId}
                    onChange={(event) =>
                      setSelectedOrder(Number(event.target.value))
                    }
                  >
                    {eligible.map((order) => (
                      <option key={order.id} value={order.id}>
                        №{order.id} · {dateLabel(order.created_at)}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <div className="form-row">
                <label className="field">
                  <span>Оценка</span>
                  <select
                    value={rating}
                    onChange={(event) => setRating(Number(event.target.value))}
                  >
                    {[5, 4, 3, 2, 1].map((value) => (
                      <option key={value} value={value}>
                        {"★".repeat(value)} · {value} из 5
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="field">
                <span>Ваш отзыв</span>
                <textarea
                  required
                  minLength={10}
                  maxLength={2000}
                  rows={4}
                  value={body}
                  aria-describedby="new-review-length"
                  onChange={(event) => setBody(event.target.value)}
                  placeholder="Что понравилось вашему питомцу?"
                />
                <span className="form-note" id="new-review-length">
                  От 10 до 2000 символов. Сейчас: {body.trim().length} / 2000.
                </span>
              </label>
              <label className="field">
                <span>Фото к отзыву (необязательно, до 3)</span>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  multiple
                  onChange={(event) =>
                    setPhotos(selectedPhotos(event.target.files))
                  }
                />
              </label>
              <ErrorNotice message={error} />
              {success && (
                <p className="success-text" role="status">
                  {success}
                </p>
              )}
              <button
                type="submit"
                className="button"
                disabled={busy || body.trim().length < 10}
              >
                {busy ? "Публикуем…" : "Опубликовать отзыв"}
              </button>
            </form>
          ) : (
            <p className="form-note">
              Сначала получите товар и подтвердите получение в{" "}
              <Link className="text-link" to="/account?tab=orders">
                истории заказов
              </Link>
              .
            </p>
          )}
          {!submitted && history.data?.length === 100 && (
            <button
              type="button"
              className="text-button"
              disabled={history.loading}
              onClick={() => setHistoryOffset((value) => value + 100)}
            >
              Проверить более ранние заказы
            </button>
          )}
          {recovery.notice}
        </div>
      ) : (
        <p className="form-note">
          Чтобы оставить отзыв после получения товара,{" "}
          <Link
            className="text-link"
            to={`/login?returnTo=${encodeURIComponent(`/product/${product.id}#reviews`)}`}
          >
            войдите в аккаунт
          </Link>
          .
        </p>
      )}
      {reviews.error && reviews.data && (
        <ErrorNotice message={reviews.error} retry={reviews.reload} />
      )}
      {reviews.loading && !reviews.data ? (
        <Loading text="Загружаем отзывы…" />
      ) : reviews.error && !reviews.data ? (
        <ErrorNotice message={reviews.error} retry={reviews.reload} />
      ) : reviews.data?.items.length ? (
        <>
          <div
            className="review-list"
            aria-busy={reviews.loading || reviews.refreshing}
          >
            {reviews.data.items.map((review) => (
              <ReviewDiscussion
                key={`${user?.id ?? "guest"}-${review.id}`}
                productId={product.id}
                review={review}
                onChanged={reload}
                onDeleted={() => {
                  setPage(1);
                  setSubmitted(false);
                  setSuccess("");
                  mine.reload();
                }}
              />
            ))}
          </div>
          {reviews.data.total > limit && (
            <nav className="pagination" aria-label="Страницы отзывов">
              <button
                className="button outline"
                disabled={page === 1 || reviews.loading}
                onClick={() => setPage((value) => value - 1)}
              >
                Назад
              </button>
              <span>
                {page} / {Math.ceil(reviews.data.total / limit)}
              </span>
              <button
                className="button outline"
                disabled={page * limit >= reviews.data.total || reviews.loading}
                onClick={() => setPage((value) => value + 1)}
              >
                Дальше
              </button>
            </nav>
          )}
        </>
      ) : (
        <p className="form-note">
          {reviews.data?.summary_total
            ? "По выбранным условиям отзывов нет. Попробуйте сбросить фильтры."
            : "Пока отзывов нет. Вы можете стать первым после получения товара."}
        </p>
      )}
      {!reviews.loading && page > 1 && !reviews.data?.items.length && (
        <button
          type="button"
          className="button outline"
          onClick={() => setPage(1)}
        >
          К первой странице отзывов
        </button>
      )}
    </section>
  );
}

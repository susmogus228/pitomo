import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { messageOf } from "../api";
import {
  Empty,
  ErrorNotice,
  Icon,
  Loading,
  PageTitle,
  PriceLabel,
  ProductImage,
  Quantity,
} from "../components";
import { money, itemCount } from "../lib";
import { operationKey } from "../purchaseTypes";
import { guestCartStorage } from "../guestCart";
import { useStore } from "../StoreContext";
import type { CartItem } from "../types";

export default function CartPage() {
  const {
    user,
    cart,
    authLoading,
    refreshCart,
    guestStorageWarning,
    guestMergePending,
    guestMergeUnconfirmed,
    guestMergeBusy,
    guestMergeResults,
    retryGuestMerge,
    changeCartQuantity,
    removeCartItem,
    restoreCartItem,
    moveCartToFavorite,
  } = useStore();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [undo, setUndo] = useState<{
    item: CartItem;
    key: string;
    owner: number | undefined;
  } | null>(null);
  const undoButton = useRef<HTMLButtonElement>(null);
  const owner = useRef(user?.id);
  owner.current = user?.id;
  const favoriteKeys = useRef(new Map<number, string>());
  useEffect(() => {
    let current = true;
    setLoading(true);
    setBusy(null);
    setUndo(null);
    setError("");
    setFeedback("");
    favoriteKeys.current.clear();
    void refreshCart()
      .catch((problem) => {
        if (current) setError(messageOf(problem));
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [user?.id, refreshCart]);
  useEffect(() => {
    if (!undo) return;
    undoButton.current?.focus();
    // Do not expire an operation whose response is being checked.
    if (busy !== null) return;
    const timer = window.setTimeout(() => setUndo(null), 15000);
    return () => window.clearTimeout(timer);
  }, [undo, busy]);
  const action = async (
    item: CartItem,
    kind: "quantity" | "remove" | "favorite",
    quantity?: number,
  ) => {
    if (busy !== null || guestMergeBusy) return;
    const expected = user?.id;
    setBusy(item.variant_id);
    setError("");
    setFeedback("");
    try {
      if (kind === "quantity")
        await changeCartQuantity(item.variant_id, quantity!);
      else if (kind === "remove") {
        await removeCartItem(item.variant_id);
        if (owner.current === expected)
          setUndo({ item, key: operationKey(), owner: expected });
      } else {
        const key = favoriteKeys.current.get(item.variant_id) || operationKey();
        favoriteKeys.current.set(item.variant_id, key);
        await moveCartToFavorite(item.variant_id, key);
        if (owner.current === expected && expected !== undefined) {
          favoriteKeys.current.delete(item.variant_id);
          setFeedback("Товар сохранён в избранном и удалён из корзины.");
        }
      }
    } catch (problem) {
      if (owner.current === expected) {
        setError(messageOf(problem));
        await refreshCart().catch(() => undefined);
      }
    } finally {
      if (owner.current === expected) setBusy(null);
    }
  };
  const restore = async () => {
    if (!undo || undo.owner !== user?.id || busy !== null) return;
    const expected = user?.id;
    setBusy(undo.item.variant_id);
    setError("");
    try {
      const message = await restoreCartItem(undo.item, undo.key);
      if (owner.current === expected) {
        setFeedback(message);
        setUndo(null);
      }
    } catch (problem) {
      if (owner.current === expected)
        setError(
          `${messageOf(problem)} Повторная проверка использует тот же ключ.`,
        );
    } finally {
      if (owner.current === expected) setBusy(null);
    }
  };
  return (
    <>
      <PageTitle
        eyebrow="Почти у вашего питомца"
        subtitle={
          cart?.total_items
            ? `${itemCount(cart.total_items)} в корзине`
            : undefined
        }
      >
        Корзина
      </PageTitle>
      {!user && (
        <div className="guest-cart-note">
          <strong>Ваша гостевая корзина</strong>
          <p>
            Товары сохраняются в этом браузере на 30 дней. После входа добавим
            их к корзине аккаунта и проверим цены и остатки. До входа сумма
            ориентировочная.
          </p>
          <Link className="text-link" to="/login?returnTo=%2Fcart">
            Войти и объединить корзины →
          </Link>
        </div>
      )}
      {guestStorageWarning && (
        <p className="form-note" role="status">
          Браузер не разрешил сохранить гостевую корзину. Она работает в этой
          вкладке; не закрывайте её до входа.
        </p>
      )}
      {user &&
        (guestMergeBusy ||
          guestMergePending ||
          guestMergeResults.some((item) => item.remaining_quantity > 0)) && (
          <section
            className="guest-merge-panel"
            aria-label="Объединение корзин"
          >
            <h2>
              {guestMergeBusy
                ? "Объединяем корзины…"
                : "Проверка гостевых товаров"}
            </h2>
            {guestMergeResults
              .filter((item) => item.remaining_quantity > 0)
              .map((item) => (
                <p key={item.variant_id}>
                  {guestCartStorage
                    .read()
                    .rows.find((row) => row.variant_id === item.variant_id)
                    ?.product_name || "Товар"}
                  : добавлено {item.added_quantity} из {item.requested_quantity}{" "}
                  шт. {item.message}
                </p>
              ))}
            {!guestMergeBusy && guestMergePending && (
              <>
                <p>
                  {guestMergeUnconfirmed
                    ? "Ответ на добавление ещё не подтверждён. Повторная проверка не добавит товары дважды."
                    : "Недоступное количество сохранено. При повторе проверим остатки заново; уже добавленные товары останутся в корзине."}
                </p>
                <button
                  className="button outline"
                  disabled={busy !== null}
                  onClick={() => void retryGuestMerge()}
                >
                  Проверить и повторить объединение
                </button>
              </>
            )}
          </section>
        )}
      <ErrorNotice
        message={error}
        retry={() =>
          void refreshCart()
            .then(() => setError(""))
            .catch((problem) => setError(messageOf(problem)))
        }
      />
      {undo && (
        <div className="cart-undo" role="status">
          <span>Удалили «{undo.item.product_name}».</span>
          <button
            ref={undoButton}
            className="text-button"
            disabled={busy !== null}
            onClick={() => void restore()}
          >
            Отменить удаление
          </button>
          <small>Доступность при восстановлении проверим заново.</small>
        </div>
      )}
      {feedback && (
        <p className="success-text" role="status">
          {feedback}
        </p>
      )}
      {loading || authLoading ? (
        <Loading />
      ) : !cart?.items.length ? (
        !error && (
          <Empty title="Пока здесь тихо">
            Пора найти что-нибудь для любимого питомца.
          </Empty>
        )
      ) : (
        <div className="checkout-layout">
          <section className="cart-list" aria-label="Товары в корзине">
            {cart.items.map((item) => (
              <article
                className={`cart-row purchase-cart-row ${user && !item.is_available ? "unavailable" : ""}`}
                key={item.variant_id}
              >
                <Link
                  className="purchase-cart-photo"
                  to={`/product/${item.product_id}?variant=${item.variant_id}`}
                  tabIndex={-1}
                  aria-hidden="true"
                >
                  <ProductImage
                    src={item.image_url || undefined}
                    alt=""
                    width={88}
                    height={104}
                    loading="lazy"
                  />
                </Link>
                <div className="cart-item-name">
                  <h2>
                    <Link
                      to={`/product/${item.product_id}?variant=${item.variant_id}`}
                    >
                      {item.product_name}
                    </Link>
                  </h2>
                  <p>
                    {item.label} ·{" "}
                    <PriceLabel
                      variant={{
                        price: item.unit_price,
                        original_price: item.original_unit_price,
                      }}
                    />{" "}
                    / шт.
                  </p>
                  {user && !item.is_available && (
                    <p className="inline-error">
                      {item.available_stock === 0
                        ? "Товар закончился. Удалите его, чтобы продолжить."
                        : `Осталось ${item.available_stock} шт. Уменьшите количество.`}
                    </p>
                  )}
                  <button
                    type="button"
                    className="text-button cart-to-favorites"
                    disabled={busy !== null || guestMergeBusy}
                    onClick={() => void action(item, "favorite")}
                  >
                    <Icon name="heart" size={15} />
                    {user ? "Перенести в избранное" : "В избранное после входа"}
                  </button>
                </div>
                <Quantity
                  value={item.quantity}
                  max={user ? Math.min(10000, item.available_stock) : 10000}
                  onChange={(quantity) =>
                    void action(item, "quantity", quantity)
                  }
                  disabled={busy !== null || guestMergeBusy}
                  label={item.product_name}
                />
                <strong className="purchase-cart-total">
                  {money(item.line_total)}
                </strong>
                <button
                  className="icon-button purchase-cart-delete"
                  aria-label={`Удалить из корзины: ${item.product_name}`}
                  disabled={busy !== null || guestMergeBusy}
                  onClick={() => void action(item, "remove")}
                >
                  <Icon name="trash" size={20} />
                </button>
              </article>
            ))}
            <Link className="text-link continue-shopping" to="/catalog">
              <Icon name="back" size={18} /> Продолжить покупки
            </Link>
          </section>
          <aside className="order-summary">
            <h2>{user ? "Ваш заказ" : "Предварительная сумма"}</h2>
            <dl>
              <div>
                <dt>Товары · {cart.total_items} шт.</dt>
                <dd>{money(cart.subtotal)}</dd>
              </div>
              <div>
                <dt>Доставка</dt>
                <dd>Демонстрационная</dd>
              </div>
              <div className="summary-total">
                <dt>Итого</dt>
                <dd>{money(cart.subtotal)}</dd>
              </div>
            </dl>
            {(!user || cart.can_checkout) &&
            busy === null &&
            !guestMergeBusy &&
            !guestMergeUnconfirmed ? (
              <Link
                className="button full-width"
                to={user ? "/checkout" : "/login?returnTo=%2Fcheckout"}
              >
                {user ? "К оформлению" : "Войти и оформить"}
                <Icon name="arrow" size={20} />
              </Link>
            ) : (
              <>
                <button className="button full-width" disabled>
                  К оформлению
                </button>
                <p className="form-note">
                  {busy !== null || guestMergeBusy
                    ? "Обновляем корзину…"
                    : guestMergeUnconfirmed
                      ? "Сначала проверьте объединение гостевых товаров."
                      : "Исправьте наличие товаров в корзине."}
                </p>
              </>
            )}
            <p className="form-note">
              {!user
                ? "После входа сумма и доступное количество могут измениться. "
                : ""}
              Тестовая оплата или оплата при получении. В этой версии реальные
              заказы не отправляются.
            </p>
          </aside>
        </div>
      )}
    </>
  );
}

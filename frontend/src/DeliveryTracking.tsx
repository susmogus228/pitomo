import { useId, useState } from "react";
import { deliveryStages, incidentLabels, isDeliveryMoving, isOrderTerminal, isPaymentReady } from "./delivery";
import type { Order } from "./types";
import "./delivery.css";
import DeliveryScene from "./DeliveryScene";
import { Icon } from "./components";

const dateTime = (value: string) => new Intl.DateTimeFormat("ru-RU", {
  dateStyle: "medium", timeStyle: "short",
}).format(new Date(value));

export function DeliveryConnection({ error, refreshing, retry }: { error: string; refreshing: boolean; retry: () => void }) {
  if (!error) return null;
  return <div className="delivery-connection" role="status">
    <span>Не удалось обновить заказ. Показаны последние полученные данные. {error}</span>
    <button type="button" className="text-button" onClick={retry} disabled={refreshing}>{refreshing ? "Обновляем…" : "Повторить"}</button>
  </div>;
}

export default function DeliveryTracking({ order }: { order: Order }) {
  const [paused, setPaused] = useState(false);
  const heading = useId();
  const tracking = order.delivery_tracking;
  if (order.delivery_method !== "delivery") return null;
  if (!tracking) return <section className="delivery-tracking"><h2>Доставка</h2><p className="form-note">Сведения об этапах доставки пока недоступны. Попробуйте обновить заказ.</p></section>;
  const activeIndex = deliveryStages.findIndex((stage) => stage.id === tracking.stage);
  const terminal = isOrderTerminal(order);
  const received = Boolean(order.received_at);
  const cancelled = terminal && !received;
  const moving = isDeliveryMoving(order);
  const animated = moving || (!terminal && tracking.incident === "engine_failure");
  const title = received ? "Посылка у вас" : cancelled ? "Доставка отменена" : tracking.incident ? "Задержка в доставке" : deliveryStages[activeIndex].label;
  const subtitle = received ? "Спасибо, что подтвердили получение. Как питомцу обновки?" : cancelled ? "Движение по заказу остановлено." : tracking.incident ? "Этап сохранён. Продолжим доставку после устранения проблемы." : !isPaymentReady(order) ? "Заказ на складе. Для отправки сначала завершите тестовую оплату." : tracking.stage === "warehouse" ? "Собираем всё, что порадует вашего питомца." : tracking.stage === "in_transit" ? "Везём немного радости к вашей двери." : "Заказ рядом. Подтвердите получение, когда посылка будет у вас.";
  return <section className={`delivery-tracking ${tracking.incident && !terminal ? "has-incident" : ""}`} aria-labelledby={heading}>
    <div className="delivery-heading"><div><p className="eyebrow">Доставка Питомо</p><h2 id={heading}>{title}</h2></div>
      {animated && <button type="button" className="delivery-motion-toggle" aria-pressed={paused} onClick={() => setPaused((value) => !value)}>{paused ? "Продолжить анимацию" : "Пауза"}</button>}
    </div>
    <p className="delivery-description" role="status">{subtitle}</p>
    <DeliveryScene order={order} paused={paused} />
    <ol className="delivery-steps" aria-label="Этапы доставки">{deliveryStages.map((stage, index) => <li key={stage.id} className={index < activeIndex || received ? "is-complete" : index === activeIndex ? "is-current" : ""} aria-current={!terminal && index === activeIndex ? "step" : undefined}>
      <span className="delivery-step-dot" aria-hidden="true">{index < activeIndex || received ? <Icon name="check" size={18} /> : index + 1}</span><span>{stage.label}</span>
    </li>)}</ol>
    {tracking.incident && !terminal && <div className="delivery-incident" role="status"><strong>{incidentLabels[tracking.incident]}</strong><p>{tracking.incident_note || "Команда магазина устраняет проблему. Обновление появится здесь."}</p></div>}
    <div className="delivery-footer"><div className="delivery-footnote"><span>Этап обновляет магазин. Это не GPS-трекер.</span>{tracking.updated_at && <time dateTime={tracking.updated_at}>Обновлено {dateTime(tracking.updated_at)}</time>}</div>
    {tracking.history.length > 0 && <details className="delivery-history"><summary>История доставки</summary><ol>{[...tracking.history].reverse().map((event, index) => <li key={`${event.occurred_at}-${index}`}><time dateTime={event.occurred_at}>{dateTime(event.occurred_at)}</time><span>{event.event_type === "incident_reported" && event.incident ? incidentLabels[event.incident] : event.event_type === "incident_resolved" ? "Проблема устранена" : event.event_type === "created" ? "Доставка оформлена" : deliveryStages.find((stage) => stage.id === event.stage)?.label}{event.note && <small>{event.note}</small>}</span></li>)}</ol></details>}
    </div>
  </section>;
}

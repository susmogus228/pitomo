import { useEffect, useState } from "react";
import { isDeliveryMoving, isOrderTerminal } from "./delivery";
import type { Order } from "./types";
import { mediaUrl } from "./media";

const media = "/media/delivery-v013/";

export default function DeliveryScene({ order, paused }: { order: Order; paused: boolean }) {
  const tracking = order.delivery_tracking!;
  const [visible, setVisible] = useState(() => document.visibilityState === "visible");
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const update = () => setVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  const moving = isDeliveryMoving(order) && !paused && visible;
  const engine = tracking.incident === "engine_failure";
  const smoke = engine && !isOrderTerminal(order) && !paused && visible;
  return <div className={`delivery-scene stage-${tracking.stage} ${tracking.incident ? `incident-${tracking.incident}` : ""} ${moving ? "is-moving" : ""} ${smoke ? "has-engine-smoke" : ""}`} aria-hidden="true">
    {failed ? <p className="delivery-art-error">Иллюстрация не загрузилась. Актуальный этап доставки указан ниже.</p> : <div className="delivery-artboard">
      <img className="delivery-scenery" src={mediaUrl(`${media}scenery.webp`)} alt="" width={2172} height={724} decoding="async" onError={() => setFailed(true)} />
      <img className="delivery-cloud delivery-cloud-one" src={mediaUrl(`${media}cloud.webp`)} alt="" width={1983} height={793} decoding="async" />
      <img className="delivery-cloud delivery-cloud-two" src={mediaUrl(`${media}cloud.webp`)} alt="" width={1983} height={793} decoding="async" />
      <div className="delivery-road-viewport"><div className="delivery-road-track" /></div>
      <div className="delivery-truck-position"><div className="delivery-vehicle"><div className="delivery-chassis">
        <img className="delivery-van-body" src={mediaUrl(`${media}${engine ? "van-engine.webp" : "van-body.webp"}`)} alt="" width={1704} height={923} decoding="async" onError={() => setFailed(true)} />
        <div className="delivery-wheel-slot delivery-wheel-back"><img className="delivery-wheel" src={mediaUrl(`${media}wheel.webp`)} alt="" width={1254} height={1254} decoding="async" /></div>
        <div className="delivery-wheel-slot delivery-wheel-front"><img className="delivery-wheel" src={mediaUrl(`${media}${tracking.incident === "flat_tire" ? "wheel-flat.webp" : "wheel.webp"}`)} alt="" width={1254} height={1254} decoding="async" /></div>
        {engine && <div className="delivery-smoke-origin">{[0, 1, 2].map((index) => <img key={index} className={`delivery-smoke-puff delivery-smoke-${index}`} src={mediaUrl(`${media}engine-smoke.webp`)} alt="" width={971} height={1619} decoding="async" />)}</div>}
      </div></div></div>
    </div>}
  </div>;
}

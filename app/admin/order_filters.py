"""Shared administrator order queue predicates for lists, counts and exports."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import and_, func, or_

from app.db.models import OrderORM

DeliveryStageFilter = Literal['warehouse', 'in_transit', 'nearby']
DeliveryIncidentFilter = Literal['flat_tire', 'overturned', 'engine_failure']
OrderQueue = Literal['active', 'warehouse', 'in_transit', 'incidents', 'awaiting_receipt', 'received']
ORDER_QUEUES = ('active', 'warehouse', 'in_transit', 'incidents', 'awaiting_receipt', 'received')


def order_criteria(*, status=None, payment_status=None, delivery_method=None, user_id=None,
                   delivery_stage=None, delivery_incident=None, received=None,
                   stale_hours=None, queue=None, now=None) -> list:
    criteria = []
    for column, value in ((OrderORM.status, status), (OrderORM.payment_status, payment_status),
                          (OrderORM.delivery_method, delivery_method), (OrderORM.user_id, user_id),
                          (OrderORM.delivery_stage, delivery_stage),
                          (OrderORM.delivery_incident, delivery_incident)):
        if value is not None:
            criteria.append(column == value)
    if received is not None:
        criteria.append(OrderORM.received_at.is_not(None) if received else OrderORM.received_at.is_(None))
    active = and_(OrderORM.status == 'created', OrderORM.received_at.is_(None))
    ready_delivery = and_(active, OrderORM.delivery_method == 'delivery', or_(
        and_(OrderORM.payment_method == 'demo', OrderORM.payment_status == 'demo_paid'),
        and_(OrderORM.payment_method == 'cod', OrderORM.payment_status == 'cod_pending')))
    if queue == 'active':
        criteria.append(active)
    elif queue == 'received':
        criteria.extend([OrderORM.status == 'created', OrderORM.received_at.is_not(None)])
    elif queue == 'incidents':
        # Warehouse incidents can be reported before payment; the operator must see them too.
        criteria.extend([active, OrderORM.delivery_method == 'delivery',
                         OrderORM.delivery_incident.is_not(None)])
    elif queue in {'warehouse', 'in_transit', 'awaiting_receipt'}:
        criteria.append(ready_delivery)
        stage = 'nearby' if queue == 'awaiting_receipt' else queue
        criteria.extend([OrderORM.delivery_stage == stage, OrderORM.delivery_incident.is_(None)])
    if stale_hours is not None:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=stale_hours)
        criteria.extend([active, OrderORM.delivery_method == 'delivery',
                         func.coalesce(OrderORM.delivery_updated_at, OrderORM.created_at) <= cutoff])
    return criteria

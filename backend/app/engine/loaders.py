"""DB -> plain engine inputs. The only engine module that touches a Session."""
from typing import Literal

from sqlmodel import Session, select

from app.engine.material_flow import FlowRecord
from app.engine.passport import build_passport
from app.models import Aggregator, Collector, Material, MaterialPassport, Recycler, Transaction


def flow_records(session: Session, group_by: Literal["collector", "area"] = "collector") -> list[FlowRecord]:
    collectors = {c.id: c for c in session.exec(select(Collector))}
    materials = {m.id: m for m in session.exec(select(Material))}
    aggregators = {a.id: a for a in session.exec(select(Aggregator))}
    recyclers = {r.id: r for r in session.exec(select(Recycler))}
    dest = {p.transaction_id: p.recycler_id for p in session.exec(select(MaterialPassport))}

    records = []
    for tx in session.exec(select(Transaction)):
        if tx.aggregator_id is None:
            continue  # not yet sold on: no flow to draw
        c = collectors[tx.collector_id]
        rec_id = dest.get(tx.id)
        records.append(FlowRecord(
            collector=c.area if group_by == "area" else f"{c.name} (#{c.id})",
            aggregator=aggregators[tx.aggregator_id].name,
            recycler=recyclers[rec_id].name if rec_id is not None else None,
            material=materials[tx.material_id].category,
            kg=tx.weight_kg,
            material_name=materials[tx.material_id].name,
        ))
    return records


def passport_for(session: Session, transaction_id: int) -> dict | None:
    tx = session.get(Transaction, transaction_id)
    if tx is None:
        return None
    mp = session.exec(
        select(MaterialPassport).where(MaterialPassport.transaction_id == tx.id)
    ).first()
    return build_passport(
        tx,
        collector=session.get(Collector, tx.collector_id),
        material=session.get(Material, tx.material_id),
        aggregator=session.get(Aggregator, tx.aggregator_id) if tx.aggregator_id else None,
        passport=mp,
        recycler=session.get(Recycler, mp.recycler_id) if mp and mp.recycler_id else None,
    )

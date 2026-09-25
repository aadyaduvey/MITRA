"""M2 demo: uv run python -m app.engine  (reads backend/data/mitra.db)."""
import json

from sqlmodel import Session, select

from app.db import engine
from app.engine.loaders import flow_records, passport_for
from app.engine.material_flow import build_sankey, kg_by_material, traced_share
from app.engine.pricing import load_prices
from app.models import MaterialPassport


def main() -> None:
    with Session(engine) as session:
        records = flow_records(session)
        share = traced_share(records)
        prices = load_prices()
        print("Total kg by material (last 14 days)")
        print(f"  {'material':<34} {'kg':>9} {'INR/kg':>7} {'value @ ref INR':>16}")
        for name, kg in kg_by_material(records, by="name").items():
            p = prices[name].ref_price_per_kg
            print(f"  {name:<34} {kg:>9,.1f} {p:>7,.0f} {kg * p:>16,.0f}")
        print(f"  {'TOTAL':<34} {share['kg_total']:>9,.1f}\n")

        print("By category (the 6 PoC classes)")
        for cat, kg in kg_by_material(records).items():
            print(f"  {cat:<8} {kg:>9,.1f}")

        sankey = build_sankey(flow_records(session, group_by="area"))
        print(f"\nSankey (collectors grouped by area): {len(sankey['nodes'])} nodes, "
              f"{len(sankey['links'])} links")
        print(f"Verified chain of custody to a recycler: {share['kg_traced']:,.1f} of "
              f"{share['kg_total']:,.1f} kg ({share['pct_traced']}%)\n")

        mp = session.exec(
            select(MaterialPassport).where(MaterialPassport.status == "delivered")
        ).first()
        print(f"Sample material passport (transaction {mp.transaction_id})")
        print(json.dumps(passport_for(session, mp.transaction_id), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

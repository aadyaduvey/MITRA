"""Reference prices from the terminal (run inside backend/).

    uv run python -m app.prices                                   # show current prices
    uv run python -m app.prices set Copper 780 --source "Jaipur kabadi market"
    uv run python -m app.prices set pet 15 --source "Aggregator rate card"   # start of a name works
    uv run python -m app.prices live                              # fetch copper from the live feed now
    uv run python -m app.prices history [Copper]                  # what changed, when, by whom

Changes apply immediately: the bot and dashboard read prices on every request.
"""
import argparse
import sys

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.db import create_db_and_tables, engine as default_engine
from app.models import IST, Material
from app.prices import live
from app.prices.service import PriceError, find_material, history, latest_updates, set_price


def show(session: Session) -> None:
    latest = latest_updates(session)
    print(f"{'Material':<34} {'Rs/kg':>8}  {'Updated':<11} Source")
    for m in session.exec(select(Material).order_by(Material.id)):
        u = latest.get(m.id)
        when = u.ts.astimezone(IST).date().isoformat() if u else "-"
        src = u.source if u else "-"
        tag = "  [live]" if m.name in live.LIVE_RULES else ""
        print(f"{m.name:<34} {m.ref_price_per_kg:>8,.2f}  {when:<11} {src}{tag}")
    key = "set" if live.api_key() else f"not set ({live.KEY_NAME} in backend/.env)"
    print(f"\nLive metal feed ({live.PROVIDER}): key {key}.")


def main(argv: list[str] | None = None, bind: Engine = default_engine) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m app.prices", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p_set = sub.add_parser("set", help="set one material's reference price (Rs/kg)")
    p_set.add_argument("material", help="name, start of a name, or id")
    p_set.add_argument("price", type=float, help="Rs per kg")
    p_set.add_argument("--source", required=True, help="where the price comes from")
    sub.add_parser("live", help="fetch live metal prices now")
    p_hist = sub.add_parser("history", help="price changes, newest first")
    p_hist.add_argument("material", nargs="?")
    args = ap.parse_args(argv)

    create_db_and_tables(bind)
    with Session(bind) as session:
        try:
            if args.cmd == "set":
                m = find_material(session, args.material)
                u = set_price(session, m, args.price, args.source)
                prev = f"Rs {u.previous_price:,.2f}" if u.previous_price is not None else "-"
                print(f"{m.name}: {prev} -> Rs {u.price_per_kg:,.2f}/kg  (source: {u.source})")
            elif args.cmd == "live":
                out = live.refresh_live(session)
                if not out["configured"]:
                    print(out["message"])
                    return 1
                for r in out["results"]:
                    print(f"{r['material']}: {r['status'].upper()}  Rs {r['old_price']:,.2f} -> "
                          f"Rs {r['new_price']:,.2f}/kg  ({r['detail']})")
                return 0 if all(r["status"] == "updated" for r in out["results"]) else 1
            elif args.cmd == "history":
                mid = find_material(session, args.material).id if args.material else None
                names = {m.id: m.name for m in session.exec(select(Material))}
                for u in history(session, mid):
                    prev = f"{u.previous_price:,.2f}" if u.previous_price is not None else "-"
                    print(f"{u.ts.astimezone(IST):%Y-%m-%d %H:%M}  {names[u.material_id]:<32} "
                          f"{prev:>9} -> {u.price_per_kg:>9,.2f}  {u.source}")
            else:
                show(session)
        except PriceError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

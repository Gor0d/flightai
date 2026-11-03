from __future__ import annotations

import argparse
import sys
import time

from .analysis import brl, render_report
from .config import load_config
from .notify import build_notifiers
from .providers import build_providers
from .service import run_search
from .storage import Storage


def _print_run(res, cfg) -> None:
    print(render_report(res.analysis, cfg))
    print(f"\nChamadas feitas: {res.calls} | Ofertas reais obtidas: {len(res.offers)}")
    for s in res.skipped:
        print(f"  ⚠ pulado — {s}")
    for e in res.errors:
        print(f"  ✖ {e}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="flighthunter", description="Monitor de tarifas aéreas")
    ap.add_argument("-c", "--config", default="config.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="busca uma vez, salva histórico e alerta")
    s.add_argument("--no-alternatives", action="store_true")
    s.add_argument("--no-notify", action="store_true")
    w = sub.add_parser("watch", help="repete a busca no intervalo da config")
    w.add_argument("--no-alternatives", action="store_true")
    sub.add_parser("history", help="menor preço por dia para as datas principais")
    sub.add_parser("check", help="mostra quais provedores/notificadores estão configurados")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # consoles Windows (cp1252) quebram com →, ✔
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    cfg = load_config(args.config)
    store = Storage(cfg.db_path)

    if args.cmd == "check":
        for p in build_providers(cfg):
            print(f"{p.name:8} {'OK' if p.is_configured() else 'sem credenciais'}")
        print("notificadores:", [type(n).__name__ for n in build_notifiers(cfg)])
        return 0
    if args.cmd == "history":
        ret = str(cfg.return_date)
        for d in map(str, cfg.main_outbounds):
            rows = store.history(d, ret)
            print(f"\nIda {d} / volta {ret}")
            for day, mn, n in rows:
                print(f"  {day}  mín {brl(mn)}/pessoa  ({n} cotações)")
            if not rows:
                print("  (sem histórico)")
        return 0

    notifiers = build_notifiers(cfg)
    if args.cmd == "search":
        res = run_search(cfg, build_providers(cfg), store, notifiers,
                         include_alternatives=not args.no_alternatives, notify=not args.no_notify)
        _print_run(res, cfg)
        return 0 if res.offers else 1
    if args.cmd == "watch":
        while True:
            res = run_search(cfg, build_providers(cfg), store, notifiers,
                             include_alternatives=not args.no_alternatives)
            _print_run(res, cfg)
            time.sleep(cfg.watch_interval_minutes * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

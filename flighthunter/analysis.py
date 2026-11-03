"""Comparação de ofertas, índice de conveniência e relatório."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import Config
from .models import FlightOffer


def convenience(o: FlightOffer, min_duration: Optional[int]) -> int:
    """0–100. Parte de 100; -30 por escala (ida+volta) e -4 por hora acima da viagem mais rápida.
    Heurística de apresentação — não altera ranking por preço."""
    score = 100.0
    if o.total_stops is not None:
        score -= 30 * o.total_stops
    if o.total_duration_minutes and min_duration:
        score -= 4 * max(o.total_duration_minutes - min_duration, 0) / 60
    return max(0, round(score))


def fmt_min(m: Optional[int]) -> str:
    return "?" if m is None else f"{m // 60}h{m % 60:02d}"


def brl(v: float, currency: str = "BRL") -> str:
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}" if currency == "BRL" else f"{currency} {s}"


def describe(o: FlightOffer, conv: Optional[int] = None) -> str:
    stops = "?" if o.total_stops is None else ("direto" if o.is_direct else f"{o.total_stops} escala(s)")
    if not o.return_details_known:
        stops += " (volta não detalhada)"
    route = " → ".join([o.outbound_segments[0].origin, *[s.destination for s in o.outbound_segments]]) \
        if o.outbound_segments else f"{o.departure_airport}→{o.arrival_airport}"
    parts = [f"{brl(o.price_per_person, o.currency)}/pessoa", o.airline or "?", stops,
             f"ida {o.outbound_date:%d/%m} {route}", f"volta {o.return_date:%d/%m}",
             f"duração {fmt_min(o.total_duration_minutes)}", f"[{o.provider}]"]
    if conv is not None:
        parts.insert(3, f"conveniência {conv}/100")
    return " · ".join(parts)


@dataclass
class Analysis:
    main: list[FlightOffer] = field(default_factory=list)          # volta == data principal
    alternatives: list[FlightOffer] = field(default_factory=list)  # outras datas
    best_direct: Optional[FlightOffer] = None
    best_overall: Optional[FlightOffer] = None
    best_ranked: Optional[FlightOffer] = None                      # respeita prefer_direct
    min_duration: Optional[int] = None


def dedupe(offers: list[FlightOffer]) -> list[FlightOffer]:
    best: dict[tuple, FlightOffer] = {}
    for o in offers:
        k = (o.fingerprint, o.currency)
        if k not in best or o.total_price < best[k].total_price:
            best[k] = o
    return list(best.values())


def analyze(offers: list[FlightOffer], cfg: Config) -> Analysis:
    offers = [o for o in dedupe(offers) if o.currency == cfg.currency]
    a = Analysis()
    a.main = sorted([o for o in offers if o.return_date == cfg.return_date
                     and o.outbound_date in cfg.main_outbounds], key=lambda o: o.total_price)
    a.alternatives = sorted([o for o in offers if o not in a.main], key=lambda o: o.total_price)
    durs = [o.total_duration_minutes for o in a.main if o.total_duration_minutes]
    a.min_duration = min(durs) if durs else None
    known = [o for o in a.main if o.total_stops is not None]
    directs = [o for o in known if o.is_direct]
    a.best_direct = directs[0] if directs else None
    a.best_overall = a.main[0] if a.main else None
    # prioridade = menor custo total; "prefer_direct" só desempata (direto até +5% do mais barato)
    a.best_ranked = a.best_overall
    if cfg.prefer_direct and a.best_direct and a.best_overall \
            and a.best_direct.price_per_person <= a.best_overall.price_per_person * 1.05:
        a.best_ranked = a.best_direct
    return a


def render_report(a: Analysis, cfg: Config, top: int = 5) -> str:
    L: list[str] = []
    L.append(f"FlightHunter AI — {cfg.origin}→{cfg.destination} | volta {cfg.return_date:%d/%m/%Y} | "
             f"{cfg.adults} adulto(s) | alvo {brl(cfg.target_price_per_person)}/pessoa")
    L.append("")
    L.append("== OPÇÕES PRINCIPAIS (volta preservada em %s) ==" % f"{cfg.return_date:%d/%m}")
    if not a.main:
        L.append("Nenhuma oferta real encontrada para as datas principais.")
    else:
        if a.best_ranked:
            L.append("Melhor opção: " + describe(a.best_ranked, convenience(a.best_ranked, a.min_duration)))
        if a.best_direct:
            L.append("Mais barata direta: " + describe(a.best_direct, convenience(a.best_direct, a.min_duration)))
        else:
            L.append("Mais barata direta: nenhuma oferta direta encontrada.")
        if a.best_overall and a.best_overall is not a.best_direct:
            L.append("Mais barata geral: " + describe(a.best_overall, convenience(a.best_overall, a.min_duration)))
        L.append("")
        for i, o in enumerate(a.main[:top], 1):
            flag = " ✔ ≤ alvo" if o.price_per_person <= cfg.target_price_per_person else ""
            L.append(f"{i}. {describe(o, convenience(o, a.min_duration))}{flag}")
    L.append("")
    L.append("== ALTERNATIVAS (outras datas — fora do requisito principal) ==")
    if not a.alternatives:
        L.append("Nenhuma.")
    for i, o in enumerate(a.alternatives[:top], 1):
        L.append(f"{i}. {describe(o, convenience(o, a.min_duration))}")
    return "\n".join(L)

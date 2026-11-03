"""Orquestra uma execução: busca → persiste → analisa → alerta."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .analysis import Analysis, analyze, brl, describe, convenience
from .config import Config
from .http import ProviderError
from .models import FlightOffer, SearchQuery
from .notify import Notifier, safe_send
from .providers.base import Provider
from .storage import Storage


@dataclass
class RunResult:
    offers: list[FlightOffer] = field(default_factory=list)
    analysis: Analysis = field(default_factory=Analysis)
    errors: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    calls: int = 0


def date_pairs(cfg: Config, include_alternatives: bool) -> list[tuple]:
    pairs = [(d, cfg.return_date) for d in cfg.main_outbounds]
    if include_alternatives:
        pairs += [p for p in cfg.alternative_pairs if p not in pairs]
    return pairs


def run_search(cfg: Config, providers: list[Provider], store: Storage,
               notifiers: list[Notifier] | None = None, include_alternatives: bool = True,
               notify: bool = True) -> RunResult:
    res = RunResult()
    run_started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pairs = date_pairs(cfg, include_alternatives)
    budget = cfg.max_calls_per_run
    for p in providers:
        if not p.is_configured():
            res.skipped.append(f"{p.name}: credenciais ausentes")
            continue
        for out, ret in pairs:
            if budget and sum(x.calls for x in providers) >= budget:
                res.errors.append(f"{p.name}: teto de {budget} chamadas/execução atingido")
                break
            q = SearchQuery(cfg.origin, cfg.destination, out, ret, cfg.adults, cfg.cabin, cfg.currency)
            try:
                res.offers += p.search(q)
            except ProviderError as e:
                res.errors.append(f"{p.name} {out}→{ret}: {e}")
            except Exception as e:  # um provedor quebrado não derruba os demais
                res.errors.append(f"{p.name} {out}→{ret}: erro inesperado {type(e).__name__}: {e}")
    res.calls = sum(p.calls for p in providers)

    # alertas comparam com o histórico ANTERIOR a esta execução
    res.analysis = analyze(res.offers, cfg)
    res.alerts = _alerts(res.analysis, cfg, store, run_started)
    store.save_offers(res.offers)
    if notify and notifiers and res.alerts:
        res.errors += safe_send(notifiers, "FlightHunter AI — oportunidade de passagem", "\n\n".join(res.alerts))
    return res


def _alerts(a: Analysis, cfg: Config, store: Storage, run_started: str) -> list[str]:
    msgs = []
    for o in a.main[:10]:
        pp = o.price_per_person
        prev_alert = store.last_alert_price(o.fingerprint)
        if prev_alert is not None and pp >= prev_alert:
            continue  # já avisado a este preço ou menor
        prev_min = store.min_price_before(str(o.outbound_date), str(o.return_date), run_started, o.currency)
        reasons = []
        if pp <= cfg.target_price_per_person:
            reasons.append(f"abaixo do alvo de {brl(cfg.target_price_per_person)}")
        if prev_min is not None and pp < prev_min:
            drop = (prev_min - pp) / prev_min * 100
            if drop >= cfg.drop_alert_pct:
                reasons.append(f"queda de {drop:.0f}% (antes {brl(prev_min)})")
            if not reasons:
                reasons.append("novo menor preço histórico")
        if reasons:
            msgs.append("; ".join(reasons).capitalize() + "\n" + describe(o, convenience(o, a.min_duration)))
            store.record_alert(o.fingerprint, pp, "; ".join(reasons), run_started)
    return msgs

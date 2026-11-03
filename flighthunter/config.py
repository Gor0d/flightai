"""Configuração: config.toml (comportamento) + variáveis de ambiente/.env (segredos)."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Config:
    origin: str = "BEL"
    destination: str = "BSB"
    preferred_outbound: date = date(2027, 1, 4)
    alternative_outbounds: list[date] = field(default_factory=lambda: [date(2027, 1, 3)])
    return_date: date = date(2027, 1, 6)
    # pares (ida, volta) fora do requisito principal; aparecem em seção separada
    alternative_pairs: list[tuple[date, date]] = field(default_factory=list)
    adults: int = 1
    cabin: str = "economy"
    currency: str = "BRL"
    prefer_direct: bool = True
    target_price_per_person: float = 1300.0
    drop_alert_pct: float = 10.0          # alerta se cair >= X% vs menor preço anterior
    providers: list[str] = field(default_factory=lambda: ["serpapi", "amadeus", "duffel"])
    max_calls_per_run: int = 12           # teto de chamadas pagas/limitadas por execução
    serpapi_return_details: int = 2       # nº de ofertas p/ buscar detalhe da volta (1 chamada extra cada)
    notifiers: list[str] = field(default_factory=lambda: ["console"])
    db_path: str = "data/flighthunter.sqlite"
    watch_interval_minutes: int = 360
    amadeus_env: str = "production"       # "test" ou "production"

    @property
    def main_outbounds(self) -> list[date]:
        return [self.preferred_outbound, *self.alternative_outbounds]

    def secret(self, name: str) -> str | None:
        return os.environ.get(name) or None


def _d(s: str) -> date:
    return date.fromisoformat(s)


def load_config(path: str | Path = "config.toml") -> Config:
    load_dotenv()
    cfg = Config()
    p = Path(path)
    if not p.exists():
        return cfg
    raw = tomllib.loads(p.read_text(encoding="utf-8"))
    trip = raw.get("trip", {})
    run = raw.get("run", {})
    for key in ("origin", "destination", "adults", "cabin", "currency", "prefer_direct",
                "target_price_per_person"):
        if key in trip:
            setattr(cfg, key, trip[key])
    if "preferred_outbound" in trip:
        cfg.preferred_outbound = _d(trip["preferred_outbound"])
    if "alternative_outbounds" in trip:
        cfg.alternative_outbounds = [_d(x) for x in trip["alternative_outbounds"]]
    if "return_date" in trip:
        cfg.return_date = _d(trip["return_date"])
    if "alternative_pairs" in trip:
        cfg.alternative_pairs = [(_d(a), _d(b)) for a, b in trip["alternative_pairs"]]
    for key in ("drop_alert_pct", "providers", "max_calls_per_run", "serpapi_return_details",
                "notifiers", "db_path", "watch_interval_minutes", "amadeus_env"):
        section = run if key in run else raw.get("alerts", {}) if key in raw.get("alerts", {}) else {}
        if key in section:
            setattr(cfg, key, section[key])
    return cfg

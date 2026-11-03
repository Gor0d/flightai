from __future__ import annotations

from ..config import Config
from ..http import HttpClient
from .amadeus import AmadeusProvider
from .base import Provider
from .duffel import DuffelProvider
from .serpapi import SerpApiProvider


def build_providers(cfg: Config, http: HttpClient | None = None) -> list[Provider]:
    """Instancia os provedores pedidos, na ordem de prioridade da config."""
    factories = {
        "serpapi": lambda: SerpApiProvider(cfg.secret("SERPAPI_API_KEY"), http, cfg.serpapi_return_details),
        "amadeus": lambda: AmadeusProvider(cfg.secret("AMADEUS_CLIENT_ID"), cfg.secret("AMADEUS_CLIENT_SECRET"),
                                           cfg.amadeus_env, http),
        "duffel": lambda: DuffelProvider(cfg.secret("DUFFEL_TOKEN"), http),
    }
    return [factories[n]() for n in cfg.providers if n in factories]

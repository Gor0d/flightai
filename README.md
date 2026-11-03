# FlightHunter AI

Monitor pessoal de tarifas aéreas. Configuração atual: **BEL → BSB**, ida 04/01/2027 (alt. 03/01), **volta 06/01/2027**, 1 adulto, econômica, BRL, alvo R$ 1.300/pessoa.

Sem dependências externas (só Python ≥ 3.11).

## Uso

```
copy .env.example .env        # preencha ao menos SERPAPI_API_KEY
python -m flighthunter check  # quais provedores estão ativos
python -m flighthunter search # busca, salva histórico, alerta
python -m flighthunter watch  # repete a cada watch_interval_minutes
python -m flighthunter history
python -m pytest              # testes
```

## Provedores

| Provedor | Credencial | Observação |
|---|---|---|
| SerpAPI (Google Flights) | `SERPAPI_API_KEY` | **Prioritário**: único que enxerga LATAM/GOL/Azul como o Google Flights. Ida+volta exige 1 chamada extra por oferta para detalhar a volta (`serpapi_return_details`, padrão 2). |
| Amadeus Self-Service | `AMADEUS_CLIENT_ID/SECRET` | `amadeus_env="test"` tem dados limitados; cobertura das brasileiras é incompleta. Confirme na documentação vigente que o portal Self-Service segue disponível para novos cadastros. |
| Duffel | `DUFFEL_TOKEN` | Permite emissão; cobertura BEL–BSB pode ser nula. Ofertas da "Duffel Airways" (sandbox) são descartadas. |

Provedor sem credencial é pulado; falha de um provedor não derruba os outros. `max_calls_per_run` limita o consumo de cota.
Sem scraping. Nenhum preço é estimado: oferta sem preço é descartada; dados não informados ficam `None`/"não detalhada".

> Os adaptadores foram escritos a partir dos formatos documentados das APIs e validados **com respostas simuladas**. Ainda não foram exercitados contra as APIs reais (sem chaves nesta sessão) — rode `search` com suas chaves e reporte qualquer divergência de campo.

## Lógica

- **Principal**: volta = 06/01 e ida em 04/01 ou 03/01. **Alternativas** (`alternative_pairs`) aparecem em seção separada.
- Ranking por menor custo total; `prefer_direct` só desempata (direto até 5% mais caro que a mais barata). Conexões entram na comparação, com índice de conveniência 0–100 (−30/escala, −4/h além da viagem mais rápida) e duração total.
- Alertas (console/Telegram/e-mail): preço ≤ alvo, queda ≥ `drop_alert_pct` vs. menor preço anterior, ou novo mínimo; não repete o mesmo preço da mesma oferta.
- Histórico em SQLite (`data/flighthunter.sqlite`).

## Estrutura

`flighthunter/` — `models.py`, `providers/`, `storage.py`, `analysis.py`, `service.py`, `notify.py`, `cli.py`. Testes em `tests/`.

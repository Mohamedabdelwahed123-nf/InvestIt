# Invesit

> **Estimation éducative, pas un conseil. / Educational estimate, not advice.**

## FR — C'est quoi ?
Invesit est un assistant éducatif pour les épargnants tunisiens. Vous dites « j'ai 1 000 TND »,
Invesit pose les questions manquantes (horizon, épargne de précaution, tolérance au risque),
puis un **calculateur sans IA** construit deux plans — *Prudent* et *Croissance* — avec des
simulations mauvais / moyen / bon scénario tirées de l'historique. Deux agents IA débattent de ces
plans, un modérateur explique le compromis, et un contrôle de sécurité filtre la réponse.
Invesit ne donne **jamais** de verdict, ne promet **aucun** rendement et ne manipule **jamais**
d'argent : vous investissez vous-même auprès d'un intermédiaire agréé par le CMF.

**Principe : « l'IA parle, le calculateur compte ».** Chaque chiffre affiché vient de Python pur
(`Decimal`, arrondi au millime). Les modèles de langage ne font qu'expliquer ces chiffres.

## EN — What is it?
Invesit is an educational assistant for Tunisian savers. You say "I have 1,000 TND", Invesit asks
the missing questions, a **no-AI calculator** builds two plans — *Cautious* and *Growth* — with
bad / average / good simulations from historical data. Two AI agents debate the plans, a moderator
explains the trade-off, and a safety check filters the answer. It never gives a verdict, never
promises returns, and never handles money.

**Principle: "the AI talks, the calculator counts."** Every number comes from plain Python with
`Decimal`; language models only explain tool outputs.

## Run it / Lancer le projet
Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Docker (optional, for Postgres/Langfuse).

```bash
cp .env.example .env        # fill in passwords; never commit .env
make install                # uv sync
make lint                   # ruff check + format check
make test                   # pytest with coverage
make up                     # Postgres 16 + pgvector and Langfuse via Docker Compose
```

Status: backend under construction.
The frontend (Next.js) comes last.

## Layout
```
backend/   calculator/ (no AI) · agents/ (LangGraph) · safety/ · api/ (FastAPI) · data/ · db/ · tests/
frontend/  Next.js (later)
```

License: see `LICENSE`.

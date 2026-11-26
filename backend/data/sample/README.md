# SAMPLE data — synthetic, NOT real

**Every fund and every price in this folder is invented.** The codes start with `SMP-`, every
name starts with `SAMPLE`, and every NAV row has `source = SAMPLE`. They exist only so the
calculator, agents and API can be built and tested before real data is available.

- `funds.csv` — 10 fictional funds, 2 per category (`bond_sicav`, `national_bond`,
  `mixed_sicav`, `equity_sicav`, `equity_fcp`). Columns: `code,name,manager,category,currency`.
- `nav_prices.csv` — daily NAVs (Monday–Friday, holidays ignored) from 2023-01-02 to 2025-12-31,
  a seeded random walk per fund, rounded to millimes. Columns: `fund_code,date,nav,source`.
- `generate.py` — deterministic generator: `uv run python -m backend.data.sample.generate`.

**This data must be replaced by real CMF data** (Conseil du Marché Financier bulletins) before
anything is shown to real users. The real parser is planned for Day 9 (`backend/data/cmf_parser.py`).
Never present numbers derived from this data as real fund performance.

Load it (after `make up` and `uv run alembic upgrade head`):

```bash
uv run python -m backend.data.load_csv            # defaults to this folder
```

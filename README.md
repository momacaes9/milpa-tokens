# Milpa Tokens

A closed-loop, food-backed harvest credit for **Tierra Viva Farm**, a fictional
5-acre farm in Toledo District, Belize, from the UNC International Consulting
Fall 2026 case competition.

**Tokens are not money.** Only Ernestine issues them, only Ernestine redeems them,
for food only. They cannot be passed between neighbors, cashed out, or earn
interest. The family's food is never part of the reserve.

Ernestine runs the system on paper (notebook, numbered paper tokens, WhatsApp voice
notes). This repo proves the rules hold and lets us test them against the case
numbers.

* Design and rules: [docs/DESIGN.md](docs/DESIGN.md)
* What a token buys: [docs/TOKEN_TABLE.md](docs/TOKEN_TABLE.md)
* Case numbers and assumptions: [config/tierra_viva.json](config/tierra_viva.json)

## Run

```bash
pip install -e .
milpa check          # config reconciles with the case's Exhibit A
milpa token-table    # what one token redeems for
python -m unittest discover -s tests
```

No runtime dependencies. Python 3.10+.

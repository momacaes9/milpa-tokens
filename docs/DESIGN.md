# Milpa Tokens: design (final model)

## The problem in the case

Ernestine Flores sells about $1,370 a year in a normal year (Exhibit A). $594 is
sold on credit, and 25% of that credit is never repaid ($149). She pays $240 a
year for pickup rides (case cash costs). In the 13 weeks before harvest she
turns away 8 to 10 buyers a week for corn and beans (Exhibit D), because she has
nowhere sealed to keep grain until then. Sealed drums cost $100 and hold about
250 lb (Exhibit E).

## The idea

A **Milpa Token** is a paper store voucher: **1 token = BZ$2 = US$1 of
Ernestine's corn or beans.** It is stamped, numbered and logged in the
**Libreta**, the notebook where she writes every credit sale and reads it back
to the buyer. Tokens are about corn and beans only.
No labor: no token is ever earned for work or hours.

Two drums:

* **Drum 1** is the family's food for six people. Never sold, never backs a token.
* **Drum 2** holds grain from crop repayments plus her own surplus (about 250 lb,
  mostly beans because beans carry 3.3 times the value of corn per lb). It backs
  every token and serves pre-harvest buyers.

## How tokens are earned (only these)

| Way | Rate | Example | Source |
|---|---|---|---|
| Repay credit in crops at harvest | corn $0.30/lb, beans $1.00/lb; $1 of crop = 1 token credited against the debt; grain into drum 2 | 10 lb corn = 3 tokens; 10 lb beans = 10 tokens | Exhibit B, deck |
| Repay credit in cash within 30 days | 5% of the payment, in tokens | $20 on time = 1 token | deck |
| Neighbor's pickup at peak harvest | half the $10 fare in tokens, a transport fare (no labor) | 12 rides = $60 cash + 60 tokens | deck |

Tokens credited for crop repayments settle debt; they never circulate. Reward
and pickup tokens are vouchers held by one named household.

## How tokens are spent

Only at Ernestine's market table, only for corn or beans from drum 2, only in
the pre-harvest gap (July-September in the model), at the case prices: 3.33 lb
of corn or 1 lb of beans per token.

## What a token is not

* **Not money.** Only Ernestine issues tokens and only Ernestine redeems them.
* **Not transferable.** Each token is logged to one holder in the Libreta.
* **Not cashable.** Never exchanged for Belize dollars.
* **No interest.** A token buys the same weight the day it is issued and the day
  it is spent.
* **Not backed by the family's food.** Only drum 2 counts.

## Rules (each enforced in `src/milpa/ledger.py` and tested)

| # | Rule | Why | Paper version |
|---|---|---|---|
| 1 | 1 token = US$1 of corn or beans; whole tokens only | Simple to count and explain | Stamped, numbered slips |
| 2 | Earned only by crop repayment, on-time cash reward, or half a pickup fare | Keeps tokens tied to grain and repayment | Libreta line for each |
| 3 | Spent only on corn or beans from drum 2, in the pre-harvest gap | Food goes out when the village is short | Voice note: "drum 2 is open" |
| 4 | Tokens outstanding (US$) never exceed drum-2 value | No promise she cannot keep | Count tokens out vs. lb in drum 2 |
| 5 | Drum 1 is never sold and never backs tokens | Family food is non-negotiable | Drum 1 painted and never opened for sale |
| 6 | Drum 2 holds at most ~250 lb | Exhibit E | One drum |
| 7 | Tokens issued in a year at most 10% of sales | Limits what she owes in grain | Running total on the Libreta cover |
| 8 | A reward that drum 2 cannot back yet waits in the Libreta | Rule 4 comes first | Cents written, token stamped later |
| 9 | No transfers, no cash-out, no interest | A voucher, not a currency | Name on every slip |
| 10 | Every change is one notebook line; a failed step writes nothing | No half-written promises | Write, read back, initial |

## Numbers (normal year)

| | Base | Conservative | Optimistic | Source |
|---|---:|---:|---:|---|
| Token cost (share of $1 face) | 75% | 90% | 60% | deck |
| Unpaid credit with the Libreta | 10% | 15% | 8% | deck (25% today, Exhibit A) |
| Credit no longer lost | $89 | $59 | $101 | $594 x (25% - unpaid) |
| Record gain net of reward tokens | $79 | $48 | $93 | 13 reward tokens x cost |
| Pickup gain net of token cost | $135 | $126 | $144 | $240 - $60 - 60 x cost |
| Drum 2 pre-harvest sales | $123 | $123 | $123 | 70% x $176 (Exhibit D, deck) |
| Tokens issued | 73 | 73 | 74 | 13-14 reward + 60 pickup |
| Share of sales (cap 10%) | 5.4% | 5.3% | 5.4% | / $1,370 |

Generated in [`outputs/annual_model.md`](../outputs/annual_model.md). The drums
cost $200 once (2 x $100, Exhibit E).

## What the replay checks

`milpa simulate` places these flows on the calendar of a normal year and runs
each one through the ledger: credit every month, on-time cash rewards, crop
repayments and the pickup at harvest, and spending plus sales in the gap. In
steady state it issues 73 tokens, sells $123 from drum 2, and drum 2 is worth at
least 2.8 times the tokens out at every month-end where tokens are out. Drum 2 is
nearly empty after the gap; that is the design, since the grain went to the
village when it was short.

## Assumptions

Every assumption is listed with its status (case-derived, pitch deck,
assumption) under `assumptions` in [`config/tierra_viva.json`](../config/tierra_viva.json).

## Why code exists at all

Ernestine runs this on paper. The code exists to **prove the rules hold** (every
rule has a test that tries to break it) and to **reproduce the deck's numbers**
from the case before anyone asks a neighbor to trust a paper slip.

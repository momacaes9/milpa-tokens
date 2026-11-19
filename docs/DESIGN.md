# Milpa Tokens: design

## The problem in the case

Ernestine Flores sells about $1,370 a year in a normal year and $900 in a bad one
(Exhibit A). 43% of sales are on credit, and 25% of that credit is never repaid
($149). In a bad year it is 55% and 40% ($196). She has no cash to hire help at
planting and harvest, the two moments her body is most stretched (Exhibit C), and
she turns away 8 to 10 buyers a week for corn and beans in the 13 weeks before
harvest (Exhibit D).

## The idea

A **Milpa Token** is a paper voucher for **one hour of work** at Tierra Viva at
planting or harvest. Ernestine pays neighbors' hours with tokens instead of cash she
does not have. Later, in the months when the village is short of food, the neighbor
brings the token back and receives food from Ernestine's **sale drums**: about
10 lb of corn per token, or the same value in beans, seed or (at harvest) fresh
produce that would otherwise spoil.

Old debts can be **paid in hands**. An hour of work cancels part of an unpaid
balance in the credit notebook. Debt labor issues no tokens; it only reduces what
is owed.

## Pegging the hour to real Belize data

The hour a token pays for is valued at the **Belize national minimum wage,
BZ$5.00 per hour (US$2.50)**, in force since 1 January 2023 (source in
[`data/belize_reference_data.csv`](../data/belize_reference_data.csv)). That wage
is used to turn unpaid debt into hours of work ("pay in hands"): $2.50 of old debt
cancelled per hour. The food a token buys (10 lb of corn, $3.00 at Ernestine's
price) is deliberately worth **more** than the cash wage. That gap is what makes a
neighbor prefer a token to cash.

## What a token is not

* **Not money.** Only Ernestine issues tokens and only Ernestine redeems them.
* **Not transferable.** Each token carries the household's name in the notebook.
  Neighbors cannot pass tokens to each other.
* **Not cashable.** Tokens are never exchanged for Belize dollars.
* **No interest.** A token buys the same basket the day it is issued and the day
  it is redeemed.
* **Not backed by the family's food.** Drum 1 feeds Ernestine's six-person
  household and is never counted as reserve.

## Rules (each one is enforced in `src/milpa/ledger.py` and tested)

| # | Rule | Why | Paper version |
|---|---|---|---|
| 1 | 1 token = 1 hour of work, whole hours only | Simple to count, easy to explain | One stamped, numbered slip per hour |
| 2 | Tokens are issued only in planting and harvest months | That is when she needs hands and has no cash | Notebook page opens only in those months |
| 3 | A token is issued only if the sale drums cover every outstanding token | No promise she cannot keep | Count tokens out vs. lb in sale drums |
| 4 | The family's food is never part of the reserve | Case: family food is non-negotiable | Drum 1 is painted and never opened for tokens |
| 5 | Max 10 tokens held per household | Limits her exposure to one family | Tally per household page |
| 6 | Tokens expire 12 months after issue | Clears old promises before the next harvest | Issue month written on each slip |
| 7 | Redemption only in windows: grain pre-harvest/storm months, seed before planting, fresh produce at harvest | Food goes out when the village is short, or when it would spoil anyway | Voice note: "this month tokens buy corn" |
| 8 | No transfers, no cash-out, no interest | Keeps it a harvest credit, not a currency | Name on every slip |
| 9 | Every change is one notebook line; a failed step writes nothing | No half-written promises | Write the line, read it back, initial it |
| 10 | A grain token may be paid as a corn-and-beans mix of the same value | Backing is counted in value, so a nearly empty drum can hold enough value without 10 lb of any one grain | "Half corn, half beans this time" |

## What the simulator found that changed the rules

* **Rule 10 came from the simulation.** In the two-year stress test, a backed
  token could not be paid because the drum held $3 of grain but neither 10 lb
  of corn nor 3 lb of beans. Allowing a mix closes that gap.
* **The peg and the in-kind rate move together.** At BZ$6 (announced, not enacted),
  10 lb of corn is worth exactly one hour's wage and the lock-in disappears. Raise
  the in-kind rate to 12 lb if the wage changes.
* **A third drum removes the cash trade-off.** With two drums, grain paid out to
  token holders is grain not sold to pre-harvest buyers (about $62 less cash in a
  normal year). With three drums, cash equals the drums-only case.

## Assumptions

Every assumption is listed with its status (case-derived, design choice,
assumption) under `assumptions` in [`config/tierra_viva.json`](../config/tierra_viva.json),
and the sourced facts are in [`docs/RESEARCH.md`](RESEARCH.md).

## Why code exists at all

Ernestine runs this on paper. The code exists to **prove the rules hold** (every
rule has a test that tries to break it) and to **simulate outcomes** from the case
numbers before anyone asks a neighbor to trust a paper slip.

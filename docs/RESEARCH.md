# Research notes

Every figure below is also a row in
[`data/belize_reference_data.csv`](../data/belize_reference_data.csv) with its
source URL and date. Research done 19 November 2026. Where something could not be
verified it is marked **NOT FOUND** and the model uses a labelled assumption instead.

## 1. Wages: what is one hour of work worth?

* **National minimum wage: BZ$5.00/hour (US$2.50), in force since 1 January 2023**
  for all categories of workers, set by Statutory Instruments 169 and 170 of 2022
  ([Government Press Office](https://www.pressoffice.gov.bz/minimum-wage-increases-for-all-categories-of-workers/)).
  This is the token's wage peg.
* **BZ$6.00 is announced but not enacted.** The Prime Minister announced a planned
  rise to BZ$6 in the State of the Nation address on 16 September 2025, and the
  San Pedro Sun reported that "no date has yet been announced"
  ([San Pedro Sun, 19 Sep 2025](https://www.sanpedrosun.com/government/2025/09/19/new-minimum-wage-proposal-divides-opinion-across-belize/)).
  On 22 August 2026 the government said it "remains committed" but that timing
  depends on the economy ([BBN](https://www.instagram.com/p/DcVL__yOVr1/)). On
  15 September 2026 it was again promised "in the near future" with no
  implementation date ([Love FM](https://lovefm.com/belize-minimum-wage-to-rise-from-5-to-6-an-hour/)).
  The model tests BZ$6 as a sensitivity, not as the base case.
* **Rural living wage:** BZ$1,076 per month, 2025 estimate
  ([Global Living Wage Coalition](https://www.globallivingwage.org/living-wage-benchmarks/living-wage-for-rural-belize/)).
  Shown for context only.
* **Toledo farm day wage: NOT FOUND.** No published figure for casual
  agricultural labor in Toledo was located. Village labor exchange may pay less
  than the minimum wage. The model uses the legal minimum and says so.

## 2. Prices (BAPIS, SIB) and the seasonal swing

The Belize Agriculture Price Information System (BAPIS, Ministry of Agriculture)
publishes weekly retail prices from 7 markets, including Punta Gorda (Toledo).

| Item | Punta Gorda, Aug 2022 (BZ$) | National avg, Dec 2023 (BZ$) | National, week of 26 Oct 2026 (BZ$) | Case price (US$) |
|---|---|---|---|---|
| White corn, lb | 0.45 | 0.70 | awaiting update | 0.30 |
| Red kidney beans, lb | 2.00 | 2.36 | 2.45 | 1.00 |
| Black beans, lb | 2.00 | 2.64 | 2.45 | (beans 1.00) |
| Green plantain, each | 0.33 | 0.49 | 0.45 | 0.25 |
| Cassava, lb | 1.25 | 1.93 | 1.70 | 0.40 |
| Sweet pepper, lb | 3.50 | 4.21 | 7.10 | ~1.50 (peppers/tomatoes/herbs) |

Sources: BAPIS issues [28/2022](https://www.agriculture.gov.bz/wp-content/uploads/2022/06/BAPIS-Volume-XIII-Issue-28-2022.pdf),
[33/2022](https://www.agriculture.gov.bz/wp-content/uploads/2022/07/BAPIS-Volume-XIII-Issue-33-2022.pdf),
[51/2023](https://www.agriculture.gov.bz/wp-content/uploads/2024/03/BAPIS-Issue-51-2023-National.pdf),
and the [BAPIS app](https://bapis.bz/home). The Statistical Institute of Belize
reports red kidney beans at BZ$2.80/lb (July 2025) and BZ$2.81/lb (July 2026)
([SIB CPI](https://sib.org.bz/statistics/economic-statistics/consumer-price-index/)).

**What this means for the model.** The case's bean price (US$1.00 = BZ$2.00)
matches Punta Gorda retail exactly. The case's corn price (US$0.30 = BZ$0.60) sits
above Punta Gorda retail in 2022 (BZ$0.45) and below the 2023 national average
(BZ$0.70). We keep the case prices, as instructed, and show the Punta Gorda price
in the lock-in table for reference.

**Seasonal swing: NOT ESTIMATED.** The two Punta Gorda reports that could be
reached (July and August 2022) show identical corn and bean prices. No Toledo
series covering harvest vs. pre-harvest months was publicly reachable; the BAPIS
app's history is not exposed as a public download. The model therefore does not
assume a pre-harvest price premium. It uses the case's own evidence of
pre-harvest scarcity: 8-10 buyers a week turned away for 13 weeks (Exhibit D).

## 3. The Toledo milpa calendar

* Toledo farmers "plant maize in May/June and beans in December", and "also plant
  small amount of maize in December, called 'Matambre' maize"
  ([Sustainable Harvest International-Belize with the Ministry of Natural Resources
  and Agriculture, Toledo, December 2013](https://repositorio.iica.int/bitstreams/821214db-6aef-4b14-8436-575200beec30/download)).
* Wet season June-October, drier from about February (case Exhibit F).
* **Harvest months are inferred, not sourced.** We place the main harvest in
  November-January (after the rains, for the May-June planting) and the 13 weeks of
  pre-harvest scarcity in July-September, with the storm month in October. In the
  bad year, storms run October-December and the harvest shrinks to January-February.
  Month-type counts match Exhibit A exactly; the placement is a labelled assumption
  in `config/tierra_viva.json` (`calendar.status`).

## 4. Community currencies and vouchers: what made them work

### Sarafu Network (Kenya)

* **RCT, Frontiers in Blockchain 2022** (Mqamelo, [doi:10.3389/fbloc.2021.739751](https://www.frontiersin.org/journals/blockchain/articles/10.3389/fbloc.2021.739751/full)).
  389 treated vs. 402 control accounts received 3 × 400 Sarafu in Nov-Dec 2020.
  After two months: wallet balance +$93.51 (p<0.05), monthly income +$23.17
  (p<0.05), food and water spending +$28.43 (p<0.1). The author's caveat bears
  directly on lock-in: tokens can only be spent with network members, so
  "recipients' expenditure is constrained by the range of available goods and
  services" nearby. Holding fees (demurrage) were used to push spending.
* **2025 user survey** ([Grassroots Economics, 21 Jul 2025](https://grassecon.substack.com/p/2025-sarafu-network-study-results)).
  855 phone interviews (Apr-Jun 2025): 84% report a positive income effect, but
  50% report challenges using Sarafu, and only 47% fully understand how it works.
  Problems named include rumors and pricing disputes. Sarafu has since moved to
  vouchers that are *promises of labor, goods or services*, which is close to
  a Milpa Token.

### Banco Palmas (Brazil)

* Founded 1998 in Conjunto Palmeira, Fortaleza. The *palma* is pegged 1:1 to the
  real, backed by reais and freely exchangeable. Local shops gave 5-10% discounts
  for paying in palmas: a built-in premium, as with the Milpa Token's +20%. In 2010,
  240 businesses accepted palmas and 42,000 were in circulation
  ([Wikipedia summary](https://en.wikipedia.org/wiki/Banco_Palmas)).
* Lesson: full backing and a visible discount built trust. Palmas, however, were
  convertible, and a convertible voucher behaves like money. Ours is deliberately
  not convertible: the only way out is food from Tierra Viva.

### Time banks

* A 2025 scoping review finds that **hoarding of time credits and a lack of
  accessible places to spend them** undermine time banks, and that trust and
  reciprocity sustain them
  ([Azizan et al., PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC13042674/)).

### Design lessons applied here

| Evidence | Failure or success driver | Milpa Token rule |
|---|---|---|
| Sarafu RCT caveat | Value depends on what tokens can buy nearby | Redeemable for staples the village is short of, at the one place that has them |
| Sarafu demurrage; time-bank hoarding | Unspent credits pile up | 12-month expiry, plus a voice-note reminder before tokens lapse |
| Sarafu survey: 47% fully understand | Complexity erodes trust | One rule: 1 token = 1 hour = 10 lb corn. Paper, read aloud, initialled |
| Banco Palmas 1:1 backing, 5-10% discount | Backing and a premium build trust | Every token backed by sale-drum grain; +20% over cash wage |
| Banco Palmas convertibility | Convertible scrip becomes money | No cash-out, no transfers, no interest |
| Sarafu pricing disputes | Unclear exchange rates cause disputes | Fixed in-kind table, same value for every item |

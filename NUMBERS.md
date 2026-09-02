# Numbers

I use this file to distinguish values mandated by the assessment from constants I choose in the implementation. I do not treat a mandated input as an arbitrary design constant because halving it would change the problem. For every implementation constant I introduce later, I will state its derivation and why I did not use a materially smaller value.

## Mandated values

| Value | Meaning | Why not half? |
| --- | --- | --- |
| Day 1 through Day 6 | Evaluation window | The supplied event stream and capitalization boundary require all six days. |
| AED 25.00 | Daily overdraft fee | It is a non-negotiable business rule; AED 12.50 would implement a different fee. |
| 0.04% per day (`0.0004`) | Positive-balance daily interest rate | It is a non-negotiable business rule; `0.0002` would under-accrue every eligible day. |
| 2 decimal places | AED amount precision | It is mandated currency precision for this exercise; one decimal place cannot represent supplied AED cents. |
| 3 decimal places | BHD amount precision | It is mandated currency precision for this exercise; reducing it loses supplied fils. |
| AED 0.00 | ACC-001 opening balance | Supplied account state. |
| BHD 0.000 | ACC-002 opening balance | Supplied account state. |
| One fee per account per day | Overdraft-fee cardinality | It is the explicit upper bound; changing it changes the rule and can duplicate fees. |
| One Day 6 capitalization credit | Interest posting cardinality | It is explicitly required; daily capitalization would alter subsequent balances. |

I treat the supplied event IDs, authorization IDs, dates, account IDs, and transaction amounts as fixture data, not configurable implementation constants. I will keep them visible in the replay fixture rather than scattering them through production logic.

## Chosen numeric representation and derived constants

I store authoritative monetary amounts as Python integers in each currency's smallest supported unit. I allow no binary floating-point amount into ledger arithmetic.

| Name | Value | Derivation or source | Why not half? | Failure boundary |
| --- | ---: | --- | --- | --- |
| `AED_MINOR_SCALE` | `100` | `10²`, from mandated AED two-decimal precision | `50` cannot represent every AED 0.01 amount and would change the currency unit | Reject an input with more than two AED decimal places |
| `BHD_MINOR_SCALE` | `1000` | `10³`, from mandated BHD three-decimal precision | `500` cannot represent every BHD 0.001 amount and would change the currency unit | Reject an input with more than three BHD decimal places |
| `INTEREST_RATE_NUMERATOR` | `1` | Reduced exact fraction for `0.04% = 4/10000 = 1/2500` | Halving to `0.5` would stop being integer arithmetic and halve the mandated rate | Used only with the denominator below; never interpreted alone |
| `INTEREST_RATE_DENOMINATOR` | `2500` | Reduced exact fraction for the mandated daily rate | `1250` would double every accrual | Denominator must be positive and paired with numerator `1` |
| `ROUNDING_MODE` | ties to even | Explicit resolution for midpoint values after exact rational interest calculation | A “half mode” is not meaningful; changing modes changes midpoint outcomes | The supplied fixture has no midpoint, but general tests must exercise one |
| `INSTALLMENT_REMAINDER_ORDINAL` | `1` | Deterministically give E10's one indivisible BHD minor unit to installment number 1, the first installment | There is no half ordinal; choosing the first is stable and requires no external data | Ordinal must identify one of E10's mandated three installments |

I use Python integers without a fixed-width overflow boundary. I leave practical amount and event capacity bounded by available memory and address that in the scale analysis instead of inventing an assessment-only maximum.

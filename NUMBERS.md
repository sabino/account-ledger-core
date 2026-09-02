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

## Chosen implementation constants

I have not selected the language, numeric representation, collection sizing, or output format yet.

I will use this table whenever I introduce one:

| Name | Value | Derivation or source | Why not half? | Failure boundary |
| --- | --- | --- | --- | --- |
| _example placeholder_ | _not selected_ | _explain_ | _explain_ | _state behavior at the limit_ |

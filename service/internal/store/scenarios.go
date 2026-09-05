package store

import "fmt"

// GeneratedCommand is a reproducible twelve-step recipe. The final step retries
// the exact first command, so it must not create another financial effect.
func GeneratedCommand(ordinal int64) Command {
	step, group := ordinal%12, ordinal/12
	if step == 11 {
		return GeneratedCommand(ordinal - 11)
	}
	source, destination := int(group%20)+1, int((group*7+3)%20)+1
	if destination == source {
		destination = destination%20 + 1
	}
	currency, small, held, captured, tieDown, tieUp := "AED", "0.01", "0.03", "0.02", "0.10", "0.30"
	if group%2 == 1 {
		source += 20
		destination += 20
		currency, small, held, captured, tieDown, tieUp = "BHD", "0.001", "0.003", "0.002", "0.010", "0.030"
	}
	c := Command{ID: fmt.Sprintf("generated-v2-%010d", ordinal), Kind: "transfer", Account: fmt.Sprintf("ACC-%03d", source), Destination: fmt.Sprintf("ACC-%03d", destination), Currency: currency, Amount: small, BookedDay: 1, ValueDay: 1}
	switch step {
	case 1:
		c.Amount = "90000" // More than the seeded total of either currency.
	case 2:
		c.Amount = "0.0001" // Too precise in both currencies; never rounded silently.
	case 3, 4, 5:
		c.Authorization = fmt.Sprintf("scenario-auth-%d", group)
		c.Kind, c.Amount = "hold", held
		if step != 3 {
			c.Kind, c.Amount = "capture", captured
		}
	case 6:
		c.Kind, c.Authorization = "capture", fmt.Sprintf("missing-auth-%d", group)
	case 7:
		if currency == "AED" {
			c.Destination = "ACC-021"
		} else {
			c.Destination = "ACC-001"
		}
	case 8:
		c.Kind, c.Amount, c.Installments = "split_transfer", "10.000", 3
		if currency == "AED" {
			c.Amount = "10.00"
		}
	case 9:
		c.Kind, c.Amount = "purchase", tieDown
	case 10:
		c.Kind, c.Amount = "purchase", tieUp
	}
	return c
}

package store

import "testing"

func TestStatementNormalSideAndWideTotals(t *testing.T) {
	for _, test := range []struct{ units, class, want string }{
		{"-10000", "liability", "10000"}, {"10000", "asset", "10000"},
		{"-9223372036854775808", "income", "9223372036854775808"},
		{"18446744073709551614", "expense", "18446744073709551614"},
	} {
		got, err := normalBalance(test.units, test.class)
		if err != nil || got.String() != test.want {
			t.Fatalf("%+v: %v %v", test, got, err)
		}
	}
	if _, err := normalBalance("bad", "asset"); err == nil {
		t.Fatal("accepted corrupt total")
	}
}

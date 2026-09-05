package delivery

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"net/http"
	"time"
)

const MaxPayload = 128 << 10

func signature(secret string, body []byte) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}

// Sender has a configured destination, never a URL from a public request.
func Sender(url, secret string) func(context.Context, []byte) error {
	client := &http.Client{Timeout: 2 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	return func(ctx context.Context, body []byte) error {
		if len(secret) < 32 || len(body) > MaxPayload {
			return errors.New("invalid delivery configuration or payload")
		}
		r, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
		if err != nil {
			return err
		}
		r.Header.Set("Content-Type", "application/json")
		r.Header.Set("X-Ledger-Signature", signature(secret, body))
		response, err := client.Do(r)
		if err != nil {
			return err
		}
		defer response.Body.Close()
		io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
		if response.StatusCode != http.StatusNoContent {
			return errors.New("notification not acknowledged")
		}
		return nil
	}
}

func Handler(secret string, accept func(context.Context, []byte) error) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if len(secret) < 32 {
			w.WriteHeader(503)
			return
		}
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, MaxPayload))
		if err != nil {
			w.WriteHeader(413)
			return
		}
		provided, err := hex.DecodeString(r.Header.Get("X-Ledger-Signature"))
		expected, _ := hex.DecodeString(signature(secret, body))
		if err != nil || !hmac.Equal(provided, expected) {
			w.WriteHeader(401)
			return
		}
		if err = accept(r.Context(), body); err != nil {
			w.WriteHeader(503)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})
}

package main

import (
	"context"
	"embed"
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/sabino/account-ledger-core/service/internal/delivery"
	"github.com/sabino/account-ledger-core/service/internal/store"
)

//go:embed web/*
var assets embed.FS

func main() {
	if len(os.Args) > 1 && os.Args[1] == "health" {
		r, e := http.Get("http://127.0.0.1:8080/readyz")
		if e != nil {
			os.Exit(1)
		}
		r.Body.Close()
		if r.StatusCode != 200 {
			os.Exit(1)
		}
		return
	}
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer cancel()
	instance := os.Getenv("INSTANCE_ID")
	if instance == "" {
		instance, _ = os.Hostname()
	}
	db, e := store.Open(ctx, os.Getenv("DATABASE_URL"), instance)
	if e != nil {
		log.Fatal(e)
	}
	defer db.Pool.Close()
	if raw := os.Getenv("CALENDAR_ENABLED"); raw != "" {
		db.CalendarEnabled, e = strconv.ParseBool(raw)
		if e != nil {
			log.Fatal("CALENDAR_ENABLED must be a boolean")
		}
	}
	if len(os.Args) > 1 && os.Args[1] == "watch" {
		proc, disk := os.Getenv("WATCH_PROC_DIR"), os.Getenv("WATCH_DISK_PATH")
		if proc == "" || disk == "" {
			log.Fatal("watcher requires explicit host metric and disk paths")
		}
		db.WatchHost(ctx, proc, disk)
		return
	}
	if len(os.Args) > 1 && os.Args[1] == "migrate" {
		if e = db.Migrate(ctx); e != nil {
			log.Fatal(e)
		}
		if e = db.Seed(ctx); e != nil {
			log.Fatal(e)
		}
		if e = db.SeedFixture(ctx); e != nil {
			log.Fatal(e)
		}
		return
	}
	secret := os.Getenv("DELIVERY_SECRET")
	urls := strings.Split(os.Getenv("DELIVERY_URLS"), ",")
	if len(secret) < 32 || urls[0] == "" {
		log.Fatal("explicit delivery endpoints and secret required")
	}
	senders := make([]func(context.Context, []byte) error, len(urls))
	for i, url := range urls {
		senders[i] = delivery.Sender(url, secret)
	}
	nextSink := 0
	db.SendNotification = func(ctx context.Context, body []byte) error {
		send := senders[nextSink%len(senders)]
		nextSink++
		return send(ctx, body)
	}
	mux := http.NewServeMux()
	mux.Handle("POST /internal/notifications", delivery.Handler(secret, db.ReceiveNotification))
	sem := make(chan struct{}, 4)
	reply := func(w http.ResponseWriter, v any, e error) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-store")
		if e != nil {
			status := 503
			message := "service temporarily unavailable"
			if errors.Is(e, store.ErrConflict) {
				status = 409
				message = e.Error()
			}
			if errors.Is(e, store.ErrCapacity) {
				status = 429
				message = e.Error()
			}
			if errors.Is(e, store.ErrStatementInput) {
				status = 400
				message = e.Error()
			}
			if errors.Is(e, store.ErrStatementAccount) {
				status = 404
				message = e.Error()
			}
			if status == 503 {
				log.Printf("request failed: %v", e)
			}
			w.WriteHeader(status)
			json.NewEncoder(w).Encode(map[string]string{"error": message})
			return
		}
		json.NewEncoder(w).Encode(v)
	}
	mux.HandleFunc("GET /readyz", func(w http.ResponseWriter, r *http.Request) {
		ctx, c := context.WithTimeout(r.Context(), time.Second)
		defer c()
		if db.Pool.Ping(ctx) != nil {
			w.WriteHeader(503)
			return
		}
		w.Write([]byte("ready"))
	})
	mux.HandleFunc("GET /api/status", func(w http.ResponseWriter, r *http.Request) {
		value, err := db.Status(r.Context())
		reply(w, value, err)
	})
	mux.HandleFunc("GET /api/accounts", func(w http.ResponseWriter, r *http.Request) {
		value, err := db.Accounts(r.Context(), "demo")
		reply(w, value, err)
	})
	mux.HandleFunc("GET /api/statements", func(w http.ResponseWriter, r *http.Request) {
		request, err := parseStatementRequest(r.URL.Query())
		if err != nil {
			reply(w, nil, err)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()
		value, err := db.Statement(ctx, "demo", request)
		reply(w, value, err)
	})
	mux.HandleFunc("GET /api/analytics", func(w http.ResponseWriter, r *http.Request) {
		currency := r.URL.Query().Get("currency")
		window := r.URL.Query().Get("window")
		seconds, ok := map[string]int32{"": 3600, "10m": 600, "1h": 3600, "24h": 86400}[window]
		if !ok || (currency != "" && currency != "AED" && currency != "BHD") {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()
		value, err := db.Analytics(ctx, "demo", currency, seconds)
		reply(w, value, err)
	})
	mux.HandleFunc("GET /api/fixture", func(w http.ResponseWriter, r *http.Request) {
		known := int64(-1)
		if value := r.URL.Query().Get("known"); value != "" {
			var err error
			known, err = strconv.ParseInt(value, 10, 64)
			if err != nil || known < 0 {
				w.WriteHeader(400)
				return
			}
		}
		value, err := db.FixtureReport(r.Context(), known)
		reply(w, value, err)
	})
	mux.HandleFunc("GET /api/journal", func(w http.ResponseWriter, r *http.Request) {
		cutoff, _ := strconv.ParseInt(r.URL.Query().Get("cutoff"), 10, 64)
		v, e := db.Journal(r.Context(), "demo", r.URL.Query().Get("account"), cutoff)
		reply(w, v, e)
	})
	mux.HandleFunc("GET /api/reconciliation", func(w http.ResponseWriter, r *http.Request) {
		v, e := db.Reconcile(r.Context(), "demo")
		reply(w, v, e)
	})
	decode := func(w http.ResponseWriter, r *http.Request, v any) error {
		r.Body = http.MaxBytesReader(w, r.Body, 4096)
		d := json.NewDecoder(r.Body)
		d.DisallowUnknownFields()
		if e := d.Decode(v); e != nil {
			return e
		}
		var extra any
		if e := d.Decode(&extra); e != io.EOF {
			return errors.New("one JSON object required")
		}
		return nil
	}
	mux.HandleFunc("POST /api/commands", func(w http.ResponseWriter, r *http.Request) {
		if e := db.Admit(r.Context()); e != nil {
			reply(w, nil, e)
			return
		}
		var c store.Command
		if e := decode(w, r, &c); e != nil {
			w.WriteHeader(400)
			return
		}
		// Public live surface cannot mint funds or invoke assessment overdraft rules.
		if c.Kind != "transfer" && c.Kind != "hold" && c.Kind != "capture" && c.Kind != "purchase" && c.Kind != "split_transfer" {
			w.WriteHeader(400)
			return
		}
		v, e := db.Process(r.Context(), "demo", c)
		reply(w, v, e)
	})
	mux.HandleFunc("POST /api/controls", func(w http.ResponseWriter, r *http.Request) {
		var c struct {
			EPS int `json:"eps"`
		}
		if e := decode(w, r, &c); e != nil || c.EPS < 0 || c.EPS > 20 {
			w.WriteHeader(400)
			return
		}
		// Stopping generation must remain possible when safety admission is closed.
		if c.EPS > 0 {
			if e := db.Admit(r.Context()); e != nil {
				reply(w, nil, e)
				return
			}
		}
		e := db.SetRate(r.Context(), int32(c.EPS))
		reply(w, map[string]int{"eps": c.EPS}, e)
	})
	mux.HandleFunc("POST /api/chaos/outbox", func(w http.ResponseWriter, r *http.Request) {
		if e := db.Admit(r.Context()); e != nil {
			reply(w, nil, e)
			return
		}
		e := db.PauseOutbox(r.Context())
		reply(w, map[string]int{"pause_seconds": 15}, e)
	})
	files, _ := fs.Sub(assets, "web")
	mux.Handle("/", http.FileServer(http.FS(files)))
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Ledger-Instance", instance)
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
		if r.Method == "POST" && r.Header.Get("Content-Type") != "application/json" {
			w.WriteHeader(415)
			return
		}
		if r.Header.Get("Sec-Fetch-Site") == "cross-site" {
			w.WriteHeader(403)
			return
		}
		select {
		case sem <- struct{}{}:
			defer func() { <-sem }()
		default:
			w.WriteHeader(429)
			return
		}
		ctx, c := context.WithTimeout(r.Context(), 6*time.Second)
		defer c()
		mux.ServeHTTP(w, r.WithContext(ctx))
	})
	server := &http.Server{Addr: ":8080", Handler: handler, ReadHeaderTimeout: 3 * time.Second, ReadTimeout: 8 * time.Second, WriteTimeout: 10 * time.Second, IdleTimeout: 30 * time.Second, MaxHeaderBytes: 8192}
	go db.Workers(ctx)
	go func() {
		<-ctx.Done()
		stop, c := context.WithTimeout(context.Background(), 8*time.Second)
		defer c()
		server.Shutdown(stop)
	}()
	log.Printf("ledger instance %s listening on :8080", instance)
	if e = server.ListenAndServe(); e != nil && !errors.Is(e, http.ErrServerClosed) {
		log.Fatal(e)
	}
}

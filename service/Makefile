.PHONY: generate format check test integration web

SQLC_IMAGE := sqlc/sqlc:1.31.1@sha256:70f53171d27b2424e9358869975455a6e955a5aa8e58a998a270a6e34e525537

generate:
	docker run --rm -u "$$(id -u):$$(id -g)" -v "$(CURDIR):/src" -w /src $(SQLC_IMAGE) generate

format:
	gofmt -w cmd internal
	cd web && npm run format

check:
	test -z "$$(gofmt -l cmd internal)"
	go vet ./...
	cd web && npm run check && npm run build

test:
	go test -race ./...

integration:
	go test -race -tags integration ./internal/store -count=1 -v

web:
	cd web && npm ci && npm run build

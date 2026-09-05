-- +goose Up
ALTER TABLE controls
  ADD COLUMN generator_token bigint NOT NULL DEFAULT 0,
  ADD COLUMN generator_until timestamptz;

-- Esquema de políticas para que Persona 1 lo convierta en una revisión Alembic.
-- Persona 2 no crea backend/alembic porque la base de migraciones es de P1.
-- Ejecutar con PRAGMA foreign_keys = ON. No modifica filas ya publicadas.

CREATE TABLE IF NOT EXISTS policy_versions (
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    normalized_json TEXT NOT NULL,
    checksum TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (policy_id, version)
);

CREATE INDEX IF NOT EXISTS idx_policy_versions_checksum ON policy_versions (checksum);

CREATE INDEX IF NOT EXISTS idx_policy_versions_created
    ON policy_versions (created_at, policy_id, version);

CREATE TABLE IF NOT EXISTS policy_activation (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    FOREIGN KEY (policy_id, version) REFERENCES policy_versions (policy_id, version)
);

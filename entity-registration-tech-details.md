# Entity Registration — Technology Details & Naming Conventions (MVP)

> Scope: streaming pipeline for Entity Registration. One generic Kafka topic (all entity types) → L1 RAW (Bronze) → L2 CDM + CDC (Silver) → canonical Kafka topic + DynamoDB. Environments: **dev / uat / prod**.

---

## 1. Environments

| Env | Purpose |
|-----|---------|
| dev  | Development / integration |
| uat  | User acceptance testing |
| prod | Production |

Naming template: wherever `<env>` appears below, substitute `dev`, `uat`, or `prod`.

---

## 2. Entity Types (MVP)

| # | Entity Type | Table suffix (snake_case) |
|---|-------------|---------------------------|
| 1 | Ppt | `ppt` |
| 2 | Vector | `vector` |
| 3 | CellLine | `cell_line` |
| 4 | ProteinExpressionBatch | `protein_expression_batch` |
| 5 | ProteinPurificationBatch | `protein_purification_batch` |
| 6 | VectorCombination | `vector_combination` |
| 7 | VectorBatch | `vector_batch` |
| 8 | CellLineBatch | `cell_line_batch` |

---

## 3. Confluent Cloud — Kafka Topics

| Purpose | Direction | Topic name (template) | dev | uat | prod |
|---------|-----------|-----------------------|-----|-----|------|
| Generic ingest (all entity types) | INPUT | `ede-<env>-registrationsync-generic` | `ede-dev-registrationsync-generic` | `ede-uat-registrationsync-generic` | `ede-prod-registrationsync-generic` |
| Canonical / CDM output | OUTPUT | `ede-<env>-registrationsync-canonical` | `ede-dev-registrationsync-canonical` | `ede-uat-registrationsync-canonical` | `ede-prod-registrationsync-canonical` |

- Cluster: **Confluent Cloud** `<CONFIRM cluster/bootstrap>`
- Auth: existing API key/secret per env `<CONFIRM>`
- Canonical topic: **log-compacted**, key = `<entity_type>#<entity_id>`

---

## 4. Databricks Unity Catalog — L1 RAW (Bronze)

**Catalog.Schema:** `sd_foundational_<env>.entity_registration`

| Layer table | dev / uat / prod fully-qualified | Notes |
|-------------|----------------------------------|-------|
| Raw landing (all types) | `sd_foundational_<env>.entity_registration.raw_landing` | immutable, append-only |
| Validated (all types) | `sd_foundational_<env>.entity_registration.raw_validated` | passed DQ; feeds L2 |
| Rejected (DLQ) | `sd_foundational_<env>.entity_registration.raw_rejected` | quarantine, replay after fix |

**Per-entity RAW tables** (demux by `entity_type`):

| Entity Type | Table (fully-qualified, `<env>`) |
|-------------|----------------------------------|
| Ppt | `sd_foundational_<env>.entity_registration.raw_ppt` |
| Vector | `sd_foundational_<env>.entity_registration.raw_vector` |
| CellLine | `sd_foundational_<env>.entity_registration.raw_cell_line` |
| ProteinExpressionBatch | `sd_foundational_<env>.entity_registration.raw_protein_expression_batch` |
| ProteinPurificationBatch | `sd_foundational_<env>.entity_registration.raw_protein_purification_batch` |
| VectorCombination | `sd_foundational_<env>.entity_registration.raw_vector_combination` |
| VectorBatch | `sd_foundational_<env>.entity_registration.raw_vector_batch` |
| CellLineBatch | `sd_foundational_<env>.entity_registration.raw_cell_line_batch` |

---

## 5. Databricks Unity Catalog — L2 CDM + CDC (Silver)

**Catalog.Schema:** `sd_integrated_<env>.entity_registration`

| Layer table | dev / uat / prod fully-qualified | Notes |
|-------------|----------------------------------|-------|
| Unified CDC (all types) | `sd_integrated_<env>.entity_registration.cdc_current` | one canonical table · SCD1 · CDF ON · maps to single canonical topic |

> L2 is **unified** (single `cdc_current`) to match the single canonical Kafka topic. Per-type CDC tables are **not** used in MVP.

---

## 6. DynamoDB

| Item | Value (template) | dev | uat | prod |
|------|------------------|-----|-----|------|
| Table name | `ede-<env>-entity-registration` `<CONFIRM>` | `ede-dev-entity-registration` | `ede-uat-entity-registration` | `ede-prod-entity-registration` |
| Partition key (PK) | `entity_id` | | | |
| Sort key (SK) | `entity_type` | | | |
| GSI1 PK | `legacy_id` | | | |
| Region | `<CONFIRM>` | | | |

---

## 7. Checkpoints (S3)

Convention: `s3://<bucket>-<env>/entity_registration/<layer>/<flow>/`

| Flow | Path (template) |
|------|-----------------|
| Bronze ingest | `s3://<bucket>-<env>/entity_registration/l1_raw/ingest/` |
| Bronze validation | `s3://<bucket>-<env>/entity_registration/l1_raw/validation/` |
| Silver CDC | `s3://<bucket>-<env>/entity_registration/l2_cdm_cdc/silver_cdc/` |
| Serving → Kafka canonical | `s3://<bucket>-<env>/entity_registration/l3_serving/kafka_out/` |
| Serving → DynamoDB | `s3://<bucket>-<env>/entity_registration/l3_serving/dynamo/` |

Bucket name `<CONFIRM>` (e.g. `sd-databricks-checkpoints`).

---

## 8. AWS Accounts

| Env | Account ID / Alias |
|-----|--------------------|
| dev  | `<CONFIRM>` |
| uat  | `<CONFIRM>` |
| prod | `<CONFIRM>` |

---

## 9. Naming Convention Reference (templates)

| Asset | Template |
|-------|----------|
| Kafka input topic | `ede-<env>-registrationsync-generic` |
| Kafka output topic | `ede-<env>-registrationsync-canonical` |
| L1 catalog.schema | `sd_foundational_<env>.entity_registration` |
| L1 raw per-type table | `sd_foundational_<env>.entity_registration.raw_<entity_snake>` |
| L2 catalog.schema | `sd_integrated_<env>.entity_registration` |
| L2 CDC table | `sd_integrated_<env>.entity_registration.cdc_current` |
| DynamoDB table | `ede-<env>-entity-registration` |
| S3 checkpoint | `s3://<bucket>-<env>/entity_registration/<layer>/<flow>/` |

---

_`<CONFIRM>` = pending exact value; share and I'll fill in._

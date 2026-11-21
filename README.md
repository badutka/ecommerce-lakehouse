# Olist E-Commerce Data Lakehouse

A data engineering portfolio project built using the Olist Brazilian E-Commerce Public Dataset. The project demonstrates the design and implementation of a lakehouse architecture using Databricks, PySpark, Delta Lake and Google Cloud Platform.

## 1. Project Overview

The objective is to transform raw e-commerce data into reliable, structured datasets suitable for downstream analytics.

The project follows a Medallion Architecture:

| Layer | Responsibility |
|---|---|
| Bronze | Ingest and preserve source data |
| Silver | Clean, type, validate and standardize source entities |
| Gold | Build analytical dimensions and fact tables |

**Technology stack**

- Databricks
- PySpark
- Delta Lake
- Unity Catalog
- GitHub
- Google Cloud Platform (integration planned)

Olist is a static historical dataset. The project may simulate recurring batch deliveries and controlled source updates, but does not claim genuine CDC or live streaming from the original dataset.

## 2. Architecture

```text
Olist CSV source files
        |
        v
     Bronze
  Raw Delta tables
        |
        v
     Silver
 Typed and validated tables
        |
        v
      Gold
 Dimensions and facts
        |
        v
   Project 2
 BigQuery + dbt
 Analytics and business KPIs
```

Project 1 focuses on data engineering and reliable data processing.

Project 2 will consume the Gold outputs and focus on analytics engineering, business-facing models and KPI definitions. Business metrics should primarily be defined in Project 2 rather than duplicated in the lakehouse.

## 3. Medallion Layers

### Bronze

**Purpose:** Preserve ingested source data with ingestion metadata.

- All nine Olist source tables loaded into Delta.
- Original source fields retained.
- Source fields initially loaded as strings.
- Metadata columns:
  - `ingestion_timestamp`
  - `source_file`
  - `batch_id`
- Initial implementation uses full-refresh/overwrite processing.

### Silver

**Purpose:** Provide typed, validated and cleaned source entities.

All nine source tables are available:

- `orders`
- `order_items`
- `payments`
- `order_reviews`
- `customers`
- `sellers`
- `products`
- `geolocation`
- `product_category_name_translation`

Transformations include data type conversion, validation, deduplication where applicable, and missing-value flags.

Silver preserves source-level entities and is not intended to become the primary home for business KPIs.

The Silver implementation is completed and committed to GitHub. Incremental processing is not yet implemented.

### Gold

**Purpose:** Provide analytical dimensions and facts with explicit grains and relationships.

The following dimensions have been implemented and validated:

| Table | Grain | Status |
|---|---|---|
| `dim_geography` | ZIP prefix + city + state | Complete |
| `dim_customers` | One row per `customer_unique_id` | Complete |
| `dim_products` | One row per `product_id` | Complete |
| `dim_sellers` | One row per `seller_id` | Complete |
| `dim_date` | One row per calendar date | In progress |

Planned fact tables:

| Table | Grain |
|---|---|
| `fact_orders` | One row per `order_id` |
| `fact_order_items` | One row per `(order_id, order_item_id)` |
| `fact_payments` | One row per `(order_id, payment_sequential)` |

## 4. Key Modeling Decisions

### Customer identity

**Decision:** Model customers using `customer_unique_id`, not `customer_id`.

Olist contains multiple `customer_id` records that can map to the same underlying shopper.

Consequences:

- `dim_customers` contains one row per `customer_unique_id`.
- `customer_sk` is generated using SHA-256.
- `customer_id` is retained in `fact_orders` for source traceability.
- Customer repeat-purchase analysis uses the underlying shopper identity.

The current customer dimension contains only identity attributes because the source does not provide sufficient reliable profile attributes to justify a richer customer profile.

### Customer geography

**Decision:** Model geography separately from customer identity.

Customer locations are associated with order records. The same shopper can appear with different delivery locations.

We do not interpret these differences as permanent customer address changes.

Consequences:

- Customer location is resolved at order grain.
- `dim_geography` represents distinct ZIP/city/state combinations.
- `fact_orders` will contain `delivery_geography_sk`.
- Customer SCD Type 2 is not implemented because the snapshot does not establish reliable historical profile changes.

### Shared geography dimension

**Decision:** Build `dim_geography` from the union of distinct customer and seller geography combinations.

Grain:

`(zip_code_prefix, city, state)`

Columns:

- `geography_sk`
- `zip_code_prefix`
- `city`
- `state`

The surrogate key is generated using SHA-256 over a stable JSON serialization of the three attributes.

ZIP prefixes are stored as strings to preserve leading zeros.

The dimension contains 15,249 validated combinations.

**Why not use ZIP prefix alone?**

ZIP prefixes are not necessarily unique across city/state combinations in the source data. The full combination is therefore used as the dimension grain.

### Geolocation enrichment

**Decision:** Keep detailed geolocation separate from the business geography dimension.

The geolocation source contains multiple coordinate points per ZIP prefix. Direct joins to raw coordinate records can multiply fact rows.

Profiling results:

- Customer geography: 15,034 combinations; 176 without exact geolocation matches.
- Seller geography: 2,296 combinations; 135 without exact geolocation matches.

Some unmatched combinations have ZIP prefixes present in geolocation but different city/state values.

Consequences:

- Geolocation is not the authority for customer or seller city/state attributes.
- Raw coordinate points are not joined directly to facts.
- A future `geolocation_by_zip` table may provide one representative coordinate per ZIP prefix.
- Missing coordinates will remain null rather than being invented.

### Product dimension

**Decision:** Model one row per `product_id`.

The dimension is enriched using a LEFT JOIN to the product category translation table.

Consequences:

- All source products are preserved, including products with missing or untranslated categories.
- Portuguese and English category names are retained.
- Source misspellings `product_name_lenght` and `product_description_lenght` are corrected in Gold aliases.
- `product_sk` is generated using SHA-256 of `product_id`.

The source contains 32,951 unique products. Two non-null categories lack translations, and 610 products have missing categories.

### Seller dimension

**Decision:** Model one row per `seller_id`.

Columns:

- `seller_sk`
- `seller_id`
- `geography_sk`

Seller geography is associated with the seller entity, so its geography foreign key belongs in `dim_sellers`, rather than being unnecessarily repeated in every order-item record.

Initially Type 1.

### Date dimension

**Decision:** Use one shared calendar dimension with integer `YYYYMMDD` keys.

The same dimension will support multiple date roles in `fact_orders`:

- Purchase date
- Approval date
- Carrier handover date
- Customer delivery date
- Estimated delivery date

This is a role-playing dimension. Missing source dates remain null; dates are not invented.

## 5. Surrogate Key Strategy

Deterministic SHA-256 keys are used for current business dimensions:

| Dimension | Natural key | Surrogate key |
|---|---|---|
| Customers | `customer_unique_id` | `customer_sk` |
| Products | `product_id` | `product_sk` |
| Sellers | `seller_id` | `seller_sk` |
| Geography | ZIP + city + state | `geography_sk` |

The date dimension uses an integer `YYYYMMDD` key instead.

Surrogate keys are generated in Project 1 and preserved in Project 2. They should not be independently regenerated using a different hashing algorithm in dbt.

If SCD Type 2 is introduced later, the surrogate key must distinguish different versions of the same natural entity.

## 6. Fact Table Design Principles

Fact tables have explicitly defined grains:

- Orders: one row per order.
- Order items: one row per order item.
- Payments: one row per payment sequence within an order.

Orders are not deduplicated by timestamp. Simultaneous orders are distinct transactions and must be retained.

Foreign keys will connect the facts to the appropriate dimensions.

Order-level business metrics and analytical KPIs will primarily be developed downstream in Project 2.

## 7. Engineering Practices and Future Work

Completed:

- Bronze and Silver Delta tables.
- Silver validation and transformations.
- GitHub integration with Databricks.
- Initial Gold dimensional modeling.
- Four validated Gold dimensions.

Planned:

- Complete `dim_date`.
- Implement and validate Gold fact tables.
- Referential integrity and fact-grain testing.
- Incremental batch processing and idempotency.
- Databricks workflow orchestration with Lakeflow Jobs.
- Automated testing and CI/CD.
- GCP integration and deployment.
- Downstream BigQuery and dbt warehouse.

## 8. Repository Development Workflow

The project uses trunk-based development with:

- `main`
- Feature branches

Current development branch: `feature/gold-layer`.

Completed Bronze and Silver implementations should not be refactored without a specific technical reason.

---

**Project status:** Gold dimensional modeling in progress.
# Data Quality, Validation and Source Data Limitations

## 1. Purpose

This document describes the data quality approach used in the Olist E-Commerce Lakehouse.

It covers:

- Validation performed across the Bronze, Silver and Gold layers.
- Structural integrity of the Gold dimensional model.
- Source-to-target reconciliation.
- Known limitations and anomalies in the Olist dataset.
- Opportunities for future data quality monitoring and analytical investigation.

An important distinction is made between:

1. **Pipeline and modeling quality:** whether data is processed, transformed and modeled correctly.
2. **Source data quality:** whether the original dataset contains missing, inconsistent or unexpected information.

A source-data anomaly should not automatically be treated as a pipeline failure. The objective is to preserve source information, identify exceptions and document their impact.

## 2. Data Quality Approach

The validation strategy focuses on several dimensions of data quality.

| Dimension | Objective | Example validation |
|---|---|---|
| Completeness | Identify missing required information | Null checks on identifiers and required fields |
| Uniqueness | Ensure records respect their expected grain | Duplicate primary and composite key checks |
| Validity | Confirm values have expected types and formats | Data type conversion and validation |
| Referential integrity | Ensure relationships resolve correctly | Foreign key orphan checks |
| Consistency | Ensure related datasets agree where expected | Source-to-target reconciliation |
| Cardinality | Prevent unintended record multiplication | Before-and-after join row counts |
| Traceability | Preserve the ability to identify source records | Ingestion metadata and retained source identifiers |

The checks were performed during the layer implementation and Gold integration review.

The current validation results describe completed notebook-based checks. A fully automated testing framework and scheduled quality monitoring are future engineering work.

## 3. Bronze Layer Validation

The Bronze layer contains all nine source datasets ingested into Delta tables.

Validation included:

- Successful ingestion of all nine source datasets.
- Preservation of original source fields.
- Addition of ingestion metadata.
- Corrupt-record inspection.

The following ingestion metadata is retained:

- `ingestion_timestamp`
- `source_file`
- `batch_id`

The corrupt-record inspection returned zero records in `_corrupt_record`.

The Bronze layer is intended to preserve the source representation rather than apply extensive business transformations.

## 4. Silver Layer Validation

The Silver layer contains nine cleaned and structured Delta tables:

- `orders`
- `order_items`
- `order_payments`
- `order_reviews`
- `customers`
- `sellers`
- `products`
- `geolocation`
- `product_category_name_translation`

Validation and transformation work included:

- Data type conversion.
- Null and invalid-value handling.
- Deduplication where applicable.
- Preservation of source identifiers.
- Validation of the resulting structured datasets.

The Silver layer provides the standardized input for Gold modeling.

The original source field names and meanings are retained where possible. Presentation-oriented naming corrections are applied in Gold rather than silently changing the source representation in Silver.

## 5. Gold Structural Validation

All eight Gold tables were persisted as Delta tables and validated after writing.

### 5.1 Table volumes

| Table | Expected grain | Rows |
|---|---|---:|
| `dim_geography` | ZIP prefix, city, state | 15,249 |
| `dim_customers` | `customer_unique_id` | 96,096 |
| `dim_products` | `product_id` | 32,951 |
| `dim_sellers` | `seller_id` | 3,095 |
| `dim_date` | Calendar date | 800 |
| `fact_orders` | `order_id` | 99,441 |
| `fact_order_items` | `order_id`, `order_item_id` | 112,650 |
| `fact_payments` | `order_id`, `payment_sequential` | 103,886 |

### 5.2 Key uniqueness and completeness

Validation was performed against the expected business or composite grain of each table.

Results included:

- `dim_geography`: 15,249 rows and 15,249 distinct geographic combinations.
- `dim_customers`: 96,096 rows with unique customer identifiers and surrogate keys.
- `dim_products`: 32,951 rows with unique product identifiers.
- `dim_sellers`: 3,095 rows with unique seller identifiers.
- `dim_date`: 800 rows with 800 distinct dates and date keys.
- `fact_orders`: 99,441 rows with 99,441 distinct order identifiers.
- `fact_order_items`: 112,650 rows with 112,650 distinct composite keys.
- `fact_payments`: 103,886 rows with 103,886 distinct composite keys.

Required identifiers and surrogate keys were checked for nulls.

Hash-based surrogate keys were also validated against their expected inputs.

### 5.3 Dimension lookup coverage

Dimension lookup coverage was checked before persisting the fact tables.

| Lookup | Missing references |
|---|---:|
| Order customer → `dim_customers` | 0 |
| Order customer geography → `dim_geography` | 0 |
| Order-item product → `dim_products` | 0 |
| Order-item seller → `dim_sellers` | 0 |
| Seller geography → `dim_geography` | 0 |

All required dimension lookups resolved successfully.

### 5.4 Null date keys

The following missing date key counts were observed in `fact_orders`:

| Date key | Missing keys |
|---|---:|
| `purchase_date_sk` | 0 |
| `approval_date_sk` | 160 |
| `carrier_date_sk` | 1,783 |
| `delivery_date_sk` | 2,965 |
| `estimated_delivery_date_sk` | 0 |

These missing key counts matched the corresponding null timestamp counts in the Silver source.

Therefore, they represent missing source timestamps rather than failed date dimension lookups.

The null values were intentionally preserved. No artificial date keys were introduced.

## 6. Referential Integrity and Join Cardinality

### 6.1 Foreign key validation

Eleven relationships were checked using orphan-record validation.

| Relationship | Orphan records |
|---|---:|
| `fact_orders.customer_sk` → `dim_customers` | 0 |
| `fact_orders.customer_geography_sk` → `dim_geography` | 0 |
| `fact_orders.purchase_date_sk` → `dim_date` | 0 |
| `fact_orders.approval_date_sk` → `dim_date` | 0 |
| `fact_orders.carrier_date_sk` → `dim_date` | 0 |
| `fact_orders.delivery_date_sk` → `dim_date` | 0 |
| `fact_orders.estimated_delivery_date_sk` → `dim_date` | 0 |
| `fact_order_items.product_sk` → `dim_products` | 0 |
| `fact_order_items.seller_sk` → `dim_sellers` | 0 |
| `fact_payments.order_id` → `fact_orders` | 0 |
| `dim_sellers.geography_sk` → `dim_geography` | 0 |

All eleven relationships passed.

### 6.2 Join cardinality validation

Dimension and fact joins were also tested to identify unintended row multiplication.

| Join scenario | Original rows | Joined rows |
|---|---:|---:|
| Orders with customer, geography and five date roles | 99,441 | 99,441 |
| Order items with products and sellers | 112,650 | 112,650 |
| Payments with orders | 103,886 | 103,886 |
| Sellers with geography | 3,095 | 3,095 |

All four tested join scenarios preserved their original record counts.

This confirms that the tested relationships did not introduce unintended row multiplication.

## 7. Source-to-Target Reconciliation

Source-to-target reconciliation was performed to confirm that the Gold transformations preserved important record counts and financial measures.

### 7.1 Order items

The Silver `order_items` source and Gold `fact_order_items` were compared.

Validation results:

- Source records: 112,650.
- Gold records: 112,650.
- Distinct composite keys: 112,650.
- Sum of `price`: matched exactly.
- Sum of `freight_value`: matched exactly.

No financial differences were introduced by the Gold transformation.

### 7.2 Payments

The Silver `order_payments` source and Gold `fact_payments` were compared.

Validation results:

- Source records: 103,886.
- Gold records: 103,886.
- Distinct composite keys: 103,886.
- Sum of `payment_value`: matched exactly.

No payment records or payment value totals were lost during Gold transformation.

### 7.3 Orders

The Silver `orders` source and Gold `fact_orders` were compared at the order grain.

Validation results:

- Source records: 99,441.
- Gold records: 99,441.
- Distinct order identifiers: 99,441.

The order-level source records were retained.

## 8. Known Source Data Issues

The following observations were identified during profiling and cross-fact reconciliation.

These are documented source-data exceptions. They were not silently corrected or removed from the Gold model.

### 8.1 Orders without order items

There are 775 orders in `fact_orders` without corresponding records in `fact_order_items`.

Order status breakdown:

| Order status | Count |
|---|---:|
| Unavailable | 603 |
| Canceled | 164 |
| Created | 5 |
| Invoiced | 2 |
| Shipped | 1 |
| **Total** | **775** |

Most of these orders are unavailable or canceled.

However, a small number have other statuses, including one shipped order.

These records are retained in the order fact because the existence of an order record should not depend on the presence of order-item records.

The absence of items is documented rather than treated as a reason to discard the order.

### 8.2 Orders without payment records

One delivered order has no corresponding record in the source payment dataset.

The order is:

`bfbd0f9bdef84302105ad712db648a6c`

Its order-item values are:

| Measure | Amount |
|---|---:|
| Item total | R$134.97 |
| Freight total | R$8.49 |

The source payment table contains no corresponding payment records for this order.

This was verified against the Silver `order_payments` dataset.

The order remains in `fact_orders`. No artificial payment record is generated.

### 8.3 Payment reconciliation differences

A per-order reconciliation compared:

`SUM(payment_value)`

against:

`SUM(price) + SUM(freight_value)`

Payments and order items were aggregated independently to the order grain before being joined.

This was necessary to avoid multiplying financial values when an order contains multiple items and multiple payment records.

The reconciliation covered:

- 98,665 orders with both item and payment records.
- A difference threshold greater than R$0.01.

Results:

| Observation | Count |
|---|---:|
| Payment total higher than item and freight total | 264 |
| Payment total lower than item and freight total | 39 |
| **Total differences** | **303** |

Additional observations:

- 299 differences occurred in delivered orders.
- 2 occurred in shipped orders.
- 2 occurred in canceled orders.
- Maximum absolute difference: R$182.81.
- The largest payment-lower discrepancy had a magnitude of R$51.62.

The direction of the discrepancy is not, by itself, evidence of an incorrect payment or financial misconduct.

Differences may require further investigation into payment processing, installments, payment types, refunds or source-system behavior.

The current project does not apply adjustments or imputation to force these amounts to balance.

The original item and payment facts are preserved independently.

### 8.4 Product category completeness

The product dimension contains 32,951 products.

Profiling identified:

- 610 products without an assigned category.
- Two distinct non-null Portuguese category values without English translations:
  - `pc_gamer`
  - `portateis_cozinha_e_preparadores_de_alimentos`

These values are preserved in the dimension.

The category translation is performed using a left join, ensuring that missing translations do not remove products.

### 8.5 Geographic coverage

The geolocation source does not contain exact matches for every customer and seller geographic combination.

Profiling identified:

- 176 distinct customer geographic combinations without an exact geolocation match.
- 135 distinct seller geographic combinations without an exact geolocation match.

An exact match here means the combination of ZIP prefix, city and state.

This should not be confused with missing geographic dimension records.

`dim_geography` is built from customer and seller geographic combinations, so all valid source combinations can be represented even when the geolocation source does not contain an exact coordinate match.

The dimension represents geographic identity, while the geolocation dataset provides coordinate information.

These are related but different concepts.

## 9. Future Data Quality and Anomaly Analysis

The source-data findings provide opportunities for additional analytical work.

They are not currently treated as reasons to alter the Gold model.

### 9.1 Payment reconciliation dashboard

A future dashboard could analyze payment discrepancies by:

- Difference amount and direction.
- Payment type.
- Installment count.
- Order status.
- Purchase date or period.
- Number of order items.
- Whether the order has one or multiple payment records.

This could help identify patterns and prioritize further investigation.

### 9.2 Missing-record monitoring

Potential future checks include:

- Orders without order items.
- Delivered orders without payment records.
- Orders with unexpected combinations of status and missing lifecycle timestamps.
- Changes in the frequency of these exceptions across source deliveries.

### 9.3 Completeness monitoring

Further analysis could track:

- Products without categories.
- Categories without translations.
- Geographic combinations without exact geolocation matches.
- Changes in missing-value rates across future source deliveries.

### 9.4 Automated quality controls

Future engineering work could turn selected validation checks into automated pipeline expectations or tests.

Potential controls include:

- Unique key expectations.
- Required identifier checks.
- Referential integrity checks.
- Source-to-target record count comparisons.
- Financial measure reconciliation.
- Threshold-based anomaly alerts.

The current project has completed the documented validation checks, but scheduled monitoring and a fully automated testing framework are not yet implemented.

## 10. Validation Status and Limitations

The completed Gold layer has passed its structural validation:

- Expected grains and row counts verified.
- Required keys checked for nulls and duplicates.
- Deterministic surrogate key generation validated.
- Dimension lookup coverage confirmed.
- Eleven foreign key relationships passed orphan-record checks.
- Four join cardinality scenarios preserved row counts.
- Source-to-Gold item and payment totals reconciled.

Known source-data exceptions remain documented and preserved.

The current validation represents checks performed against the available historical Olist snapshot. It does not establish how the model will behave under future incremental deliveries, changing source records or production scheduling.

Those behaviours will require additional testing as incremental processing, orchestration and automated quality controls are implemented.

## 11. Future Work

Planned improvements include:

- Automated data quality tests.
- Pipeline expectations and failure handling.
- Incremental source-to-target reconciliation.
- Monitoring of source-data anomaly rates.
- Payment reconciliation and anomaly analysis dashboard.
- Operational quality metrics and alerting.

The goal is to evolve from one-time validation of a historical dataset towards repeatable, observable data quality controls.
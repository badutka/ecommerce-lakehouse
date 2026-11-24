# Gold Layer – Data Modeling and Design Decisions

## 1. Purpose and Scope

This document describes the dimensional model implemented in the Gold layer of the Olist E-Commerce Lakehouse.

It explains the structure of the model, the grain of each table, key strategies, relationships, dimensional modeling decisions and potential future evolution.

The objective is not only to describe the resulting tables, but also to explain why they were designed this way.

The Gold layer is built from the cleaned and validated Silver datasets and consists of:

- Five dimension tables.
- Three fact tables.

The model is designed to support analytical workloads while preserving source identifiers, maintaining referential integrity and avoiding incorrect aggregation across different business-process grains.

## 2. Dimensional Model Overview

### 2.1 Gold tables

| Table | Type | Grain |
|---|---|---|
| `dim_customers` | Dimension | One row per `customer_unique_id` |
| `dim_geography` | Dimension | One row per ZIP prefix, city and state combination |
| `dim_products` | Dimension | One row per `product_id` |
| `dim_sellers` | Dimension | One row per `seller_id` |
| `dim_date` | Dimension | One row per calendar date |
| `fact_orders` | Fact | One row per `order_id` |
| `fact_order_items` | Fact | One row per `order_id` and `order_item_id` |
| `fact_payments` | Fact | One row per `order_id` and `payment_sequential` |

### 2.2 Modeling approach

The model follows a dimensional modeling approach:

- Dimensions contain descriptive attributes used to filter, group and analyze business events.
- Fact tables contain records representing business processes and their associated measures.
- Surrogate keys provide internal identifiers for dimension records.
- Foreign keys connect facts to their descriptive dimensions.

Orders, order items and payments are modeled as separate fact tables because they represent different grains and business processes.

This separation prevents unintended row multiplication when combining records with different cardinalities.

## 3. Surrogate Key Strategy

### 3.1 Why use surrogate keys?

A surrogate key is an identifier generated for use within the analytical model rather than an identifier originating from the source business system.

The model uses surrogate keys to decouple its internal relationships from source-system identifiers and to establish a consistent dimension key strategy.

Most dimension keys are generated using deterministic SHA-256 hashes.

### 3.2 Why deterministic hash keys?

A common alternative is to generate sequential surrogate keys using database identity columns or sequences.

For this project, deterministic hash keys were selected because they provide:

- **Reproducibility:** the same input produces the same key across repeated executions.
- **Execution-order independence:** keys do not depend on distributed row ordering or processing sequence.
- **Stable identification:** the same business identifier or attribute combination can be resolved consistently.
- **A foundation for incremental processing:** deterministic keys can support repeatable dimension lookups and future upsert logic.

Deterministic keys do not, by themselves, implement incremental processing, idempotency or historical tracking. Those behaviours still require appropriate processing logic and validation.

### 3.3 Hash input by dimension

| Dimension | Hash input | Key column |
|---|---|---|
| `dim_customers` | `customer_unique_id` | `customer_sk` |
| `dim_geography` | ZIP prefix, city and state | `geography_sk` |
| `dim_products` | `product_id` | `product_sk` |
| `dim_sellers` | `seller_id` | `seller_sk` |

For the composite geography key, the input is represented as a structured object with a consistent field order before hashing.

This is important because a composite key must have a stable serialization convention. Field order, null handling and string representation must remain consistent whenever the key is regenerated.

### 3.4 Why not hash the date key?

`dim_date` uses an integer surrogate key in `YYYYMMDD` format.

For example:

| Date | `date_sk` |
|---|---:|
| 2018-01-01 | 20180101 |
| 2018-01-02 | 20180102 |

A calendar date already has a natural, stable and compact representation. Hashing it would add complexity without providing a meaningful benefit.

This is a deliberate exception to the SHA-256 strategy.

### 3.5 Limitations of deterministic hash keys

Hash-based keys have trade-offs:

- They are less human-readable than natural or sequential identifiers.
- The serialization convention must remain stable.
- A change to an attribute used in a composite hash creates a different key.
- A hash key does not automatically handle changes to descriptive dimension attributes.
- SHA-256 collisions are extremely unlikely, but uniqueness should still be validated rather than assumed.

The implementation validates key uniqueness and consistency against the selected source identifiers or attribute combinations.

## 4. Dimension Design

### 4.1 `dim_customers`

**Purpose**

Represents the underlying shoppers in the Olist dataset.

**Grain**

One row per `customer_unique_id`.

**Keys**

- Primary key: `customer_sk`
- Business identifier: `customer_unique_id`
- Surrogate key: SHA-256 hash of `customer_unique_id`

**Why use `customer_unique_id` rather than `customer_id`?**

The source dataset contains two customer identifiers with different meanings:

- `customer_id` identifies a customer record associated with an order.
- `customer_unique_id` identifies the underlying shopper across potentially multiple customer records.

Multiple `customer_id` values can therefore map to the same `customer_unique_id`.

Using `customer_id` as the dimension grain would represent these records separately, even when they refer to the same underlying shopper.

The dimension consequently uses `customer_unique_id` as its grain.

The original `customer_id` is retained in `fact_orders` to preserve the relationship to the source order record.

The customer surrogate key is resolved through this lookup:

`orders.customer_id` → `customers.customer_id` → `customers.customer_unique_id` → `dim_customers.customer_unique_id` → `customer_sk`

**Attributes**

The current dimension contains the customer surrogate key and underlying unique customer identifier.

Customer geography is not stored in this dimension.

This is intentional: the source location is associated with customer records and order deliveries. It should not automatically be interpreted as a permanent customer profile address.

**History management**

The current dimension uses Type 1 semantics. No Type 2 history tracking is implemented.

This is a deliberate decision because the source is a historical snapshot and does not establish a reliable sequence of permanent customer attribute changes.

For example, a change in delivery location could reflect a different delivery destination or a gift rather than a change in the shopper's home address.

**Potential future evolution**

Type 2 could be considered if reliable historical versions of customer attributes become available.

That would require:

- A clearly defined set of historically tracked attributes.
- Reliable identification of changes between source versions.
- Effective start and end timestamps.
- A current-record indicator.
- A strategy for resolving fact records to the correct historical customer version.

The current source does not justify reconstructing such history.

### 4.2 `dim_geography`

**Purpose**

Provides a reusable geographic dimension for customer and seller locations.

**Grain**

One row per combination of:

- `zip_code_prefix`
- `city`
- `state`

**Keys**

- Primary key: `geography_sk`
- Business identity: ZIP prefix, city and state
- Surrogate key: SHA-256 hash of the structured attribute combination

**Why is ZIP prefix not sufficient?**

A ZIP prefix alone does not uniquely identify a geographic combination in this source dataset.

The same ZIP prefix can appear with different city or state values.

Using only the ZIP prefix would risk combining records that the source represents as different geographic combinations.

The dimension therefore uses all three attributes as its business identity.

**Source construction**

The dimension is built from the union of distinct customer and seller geographic combinations.

This ensures that both customer and seller locations can be represented, even when an exact match is absent from the geolocation source.

**Geography versus geolocation**

The dimension represents a geographic business identity, not a coordinate-based location.

A seller can resolve to a row in `dim_geography` even if the corresponding ZIP prefix, city and state combination is missing from the geolocation source.

The absence of an exact coordinate match does not mean the geographic dimension record is missing.

**Relationships**

- `fact_orders.customer_geography_sk` → `dim_geography.geography_sk`
- `dim_sellers.geography_sk` → `dim_geography.geography_sk`

**History management**

The current dimension uses Type 1 semantics.

The model does not attempt to reconstruct historical changes to geographic attributes.

If future requirements introduce historical geography tracking, the business meaning of a change to ZIP prefix, city or state must first be established.

### 4.3 `dim_products`

**Purpose**

Provides descriptive product attributes for order-item analysis.

**Grain**

One row per `product_id`.

**Keys**

- Primary key: `product_sk`
- Business identifier: `product_id`
- Surrogate key: SHA-256 hash of `product_id`

**Source construction**

The dimension is built from the Silver `products` table and enriched with English product category names through a left join to `product_category_name_translation`.

The left join is intentional: all products are retained, including products with missing or untranslated categories.

**Modeling decisions**

The source contains misspelled field names:

- `product_name_lenght`
- `product_description_lenght`

These are corrected in Gold to:

- `product_name_length`
- `product_description_length`

The Silver layer remains source-faithful.

Missing category values and missing translations are preserved rather than replaced with invented categories.

**History management**

The dimension currently uses Type 1 semantics.

The available source is a snapshot and does not provide a reliable history of product attribute changes.

If future source versions provide historical product attributes, Type 2 could be evaluated for attributes where historical reporting is meaningful.

### 4.4 `dim_sellers`

**Purpose**

Provides seller identifiers and their associated geographic location.

**Grain**

One row per `seller_id`.

**Keys**

- Primary key: `seller_sk`
- Business identifier: `seller_id`
- Surrogate key: SHA-256 hash of `seller_id`
- Foreign key: `geography_sk`

**Geography relationship**

The seller's geography is resolved using the complete combination of ZIP prefix, city and state.

The resulting `geography_sk` references `dim_geography`.

**Why store geography in the seller dimension?**

Seller geography is an attribute of the seller, not of an individual order item.

Keeping it in `dim_sellers` avoids repeating the seller's geographic attributes in every order-item fact record.

Analytical queries can retrieve seller geography through the seller dimension.

**History management**

The dimension currently uses Type 1 semantics.

A future Type 2 implementation could preserve seller attribute changes if reliable historical source versions become available.

Such an implementation would need to define how historical seller versions are associated with order-item facts.

### 4.5 `dim_date`

**Purpose**

Provides calendar attributes for order lifecycle analysis.

**Grain**

One row per calendar date.

**Keys**

- Primary key: `date_sk`
- Natural date attribute: `date`
- Surrogate key: integer in `YYYYMMDD` format

**Date coverage**

The date dimension is generated using the minimum and maximum non-null dates found across five order timestamp fields:

- `order_purchase_timestamp`
- `order_approved_at`
- `order_delivered_carrier_date`
- `order_delivered_customer_date`
- `order_estimated_delivery_date`

Every calendar date between the minimum and maximum is generated, including dates with no corresponding order event.

**Attributes**

The dimension includes:

- Calendar year.
- Quarter.
- Month and month name.
- Day of month.
- Day of week and day name.
- Week of year.
- Weekend indicator.

The week-of-year attribute follows Spark's `weekofyear()` convention. Calendar year and week number should not automatically be interpreted as an ISO week-based year and week pair around New Year.

**Role-playing dimension**

A single date dimension is reused for multiple date roles in `fact_orders`.

| Fact column | Date role |
|---|---|
| `purchase_date_sk` | Purchase date |
| `approval_date_sk` | Approval date |
| `carrier_date_sk` | Carrier handover date |
| `delivery_date_sk` | Customer delivery date |
| `estimated_delivery_date_sk` | Estimated delivery date |

This avoids creating separate date dimensions for each order lifecycle event.

**Null handling**

Source timestamps that are null remain null in the corresponding fact date key.

No artificial date keys are created for missing events.

This preserves the distinction between an event with no recorded timestamp and a real calendar date.

## 5. Fact Table Design

### 5.1 `fact_orders`

**Purpose**

Represents orders and their lifecycle information.

**Grain**

One row per `order_id`.

**Source**

`lakehouse.silver.orders`

**Keys and relationships**

- Primary key: `order_id`
- Foreign key: `customer_sk` → `dim_customers`
- Foreign key: `customer_geography_sk` → `dim_geography`
- Five date foreign keys → `dim_date`

**Customer relationship**

The source `customer_id` is retained.

The customer surrogate key is resolved through the source customer mapping to `customer_unique_id`.

This allows multiple order records associated with the same underlying shopper to reference the same customer dimension row.

**Customer geography**

The customer geography key is resolved using the customer's ZIP prefix, city and state.

This represents the location attributes associated with the order's customer record, not necessarily a permanent customer profile location.

**Date relationships**

The fact contains five date keys corresponding to different stages of the order lifecycle.

The original source timestamps are retained alongside the date keys.

This preserves timestamp-level detail while providing efficient relationships to the shared date dimension.

**Null handling**

Missing approval, carrier and delivery timestamps are preserved as null date keys.

The missing key counts were compared against the corresponding source timestamp null counts and matched exactly.

This confirms that the null keys reflect missing source timestamps rather than failed dimension lookups.

### 5.2 `fact_order_items`

**Purpose**

Represents the individual items included in orders.

**Grain**

One row per combination of `order_id` and `order_item_id`.

**Source**

`lakehouse.silver.order_items`

**Composite key**

The combination of `order_id` and `order_item_id` uniquely identifies an order-item record.

**Foreign keys**

- `product_sk` → `dim_products.product_sk`
- `seller_sk` → `dim_sellers.seller_sk`

The original `product_id` and `seller_id` values are retained alongside the surrogate keys for source traceability.

**Measures and attributes**

- `price`
- `freight_value`
- `shipping_limit_date`

**Why keep seller geography out of the fact?**

Seller geography is available through:

`fact_order_items.seller_sk` → `dim_sellers.geography_sk` → `dim_geography`

Repeating seller geography directly in every order-item record would introduce unnecessary duplication.

**Validation considerations**

The source and fact record counts match.

The composite key is unique, all product and seller lookups resolve, and the sums of price and freight value match the Silver source.

### 5.3 `fact_payments`

**Purpose**

Represents payment records associated with orders.

**Grain**

One row per combination of `order_id` and `payment_sequential`.

**Source**

`lakehouse.silver.order_payments`

**Composite key**

The combination of `order_id` and `payment_sequential` identifies an individual payment record within an order.

**Relationship**

- Foreign key: `order_id` → `fact_orders.order_id`

**Measures and attributes**

- `payment_value`
- `payment_type`
- `payment_installments`

**Why is payment a separate fact table?**

An order can have multiple payment records.

Combining payment records directly with order-item records would create a many-to-many join between two different grains.

For example, an order with multiple items and multiple payments could produce duplicated financial values if the tables were joined without first aggregating to the order grain.

Keeping payments separate preserves their original grain and allows payment analysis without introducing unintended row multiplication.

The source payment type `not_defined` is retained rather than converted into an invented category.

## 6. Slowly Changing Dimension Strategy

### 6.1 Current implementation

The current dimensions use Type 1 semantics.

This means the model represents the available descriptive attributes without maintaining historical versions of dimension records.

No Type 2 history tracking has been implemented.

### 6.2 Why not implement Type 2 immediately?

The Olist dataset is a historical snapshot rather than a sequence of reliable source extracts with historical attribute changes.

A Type 2 implementation requires more than adding effective dates and a current-record flag.

It requires reliable evidence that an attribute changed, knowledge of when that change became effective, and a consistent method of identifying the relevant historical version.

Without those inputs, implementing Type 2 would risk creating artificial history.

### 6.3 Potential future Type 2 implementation

Type 2 could be introduced if future source deliveries provide reliable historical changes for selected dimensions.

A typical implementation would introduce:

- A new surrogate key for every dimension version.
- Effective start timestamp.
- Effective end timestamp.
- Current-record indicator.
- Change detection logic.
- Historical version resolution when loading fact records.

The choice of which attributes should be tracked historically should be based on business requirements.

For example, changes in seller geography might be meaningful for historical seller performance analysis, whereas a change in a customer's delivery location should not automatically be treated as a permanent customer profile change.

Type 2 is a potential future capability, not a requirement that should be implemented without appropriate source history.

## 7. Relationships and Referential Integrity

The Gold model contains eleven validated relationships.

| From | To | Relationship |
|---|---|---|
| `fact_orders.customer_sk` | `dim_customers.customer_sk` | Many-to-one |
| `fact_orders.customer_geography_sk` | `dim_geography.geography_sk` | Many-to-one |
| `fact_orders.purchase_date_sk` | `dim_date.date_sk` | Many-to-one |
| `fact_orders.approval_date_sk` | `dim_date.date_sk` | Many-to-one |
| `fact_orders.carrier_date_sk` | `dim_date.date_sk` | Many-to-one |
| `fact_orders.delivery_date_sk` | `dim_date.date_sk` | Many-to-one |
| `fact_orders.estimated_delivery_date_sk` | `dim_date.date_sk` | Many-to-one |
| `fact_order_items.product_sk` | `dim_products.product_sk` | Many-to-one |
| `fact_order_items.seller_sk` | `dim_sellers.seller_sk` | Many-to-one |
| `fact_payments.order_id` | `fact_orders.order_id` | Many-to-one |
| `dim_sellers.geography_sk` | `dim_geography.geography_sk` | Many-to-one |

All eleven relationships passed orphan-record checks.

Join cardinality checks were also performed to ensure that dimension joins did not unexpectedly multiply fact records.

## 8. Planned Model Visuals

### 8.1 Gold dimensional model ERD

<!-- TODO: Add the Gold dimensional model ERD.
     Include all eight Gold tables, columns, data types,
     primary keys and foreign key relationships.
     Generate from the persisted Gold schemas. -->

The ERD will describe the structure and relationships of the Gold model. It is distinct from the pipeline lineage graph.

### 8.2 Column-level lineage examples

<!-- TODO: Add Unity Catalog column-level lineage screenshots.
     Suggested examples: fact_orders and fact_payments.
     Show selected columns flowing from source through
     Bronze, Silver and Gold. -->

These examples will demonstrate how selected attributes are transformed through the lakehouse layers.

## 9. Future Modeling and Engineering Considerations

The current dimensional model provides a foundation for future platform enhancements.

Potential areas of evolution include:

- Incremental processing and Delta MERGE operations.
- Idempotent dimension and fact loading.
- Reliable historical source snapshots.
- Selective Type 2 history tracking when supported by source data.
- Declarative pipeline definitions and managed expectations.
- Automated referential integrity and data quality tests.
- Data lineage and column-level lineage documentation.
- Further analytical models built on top of the Gold layer.

Any future changes to the model should preserve clearly defined grain, stable key semantics and explicit relationship validation.

from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities import bronze_schemas  # type: ignore


BASE_PATH = "/Volumes/lakehouse/raw/olist_source"

BRONZE_SCHEMAS = {
    "orders": bronze_schemas.BRONZE_ORDERS_SCHEMA,
    "customers": bronze_schemas.BRONZE_CUSTOMERS_SCHEMA,
    "products": bronze_schemas.BRONZE_PRODUCTS_SCHEMA,
    "sellers": bronze_schemas.BRONZE_SELLERS_SCHEMA,
    "order_reviews": bronze_schemas.BRONZE_ORDER_REVIEWS_SCHEMA,
    "order_payments": bronze_schemas.BRONZE_ORDER_PAYMENTS_SCHEMA,
    "order_items": bronze_schemas.BRONZE_ORDER_ITEMS_SCHEMA,
    "geolocation": bronze_schemas.BRONZE_GEOLOCATION_SCHEMA,
    "product_category_name_translation": bronze_schemas.BRONZE_PRODUCT_CATEGORY_TRANSLATION_SCHEMA,
}

SOURCE_CONFIG = {
    "orders": {
        "file": "olist_orders_dataset.csv",
    },
    "customers": {
        "file": "olist_customers_dataset.csv",
    },
    "products": {
        "file": "olist_products_dataset.csv",
    },
    "sellers": {
        "file": "olist_sellers_dataset.csv",
    },
    "order_reviews": {
        "file": "olist_order_reviews_dataset.csv",
    },
    "order_payments": {
        "file": "olist_order_payments_dataset.csv",
    },
    "order_items": {
        "file": "olist_order_items_dataset.csv",
    },
    "geolocation": {
        "file": "olist_geolocation_dataset.csv",
    },
    "product_category_name_translation": {
        "file": "product_category_name_translation.csv",
    },
}

BRONZE_QUALITY_RULES = {

    "orders": {
        "warn_rules": {
            "valid_order_id": "order_id IS NOT NULL",
            "valid_customer_id": "customer_id IS NOT NULL",
            "no_corrupt_records": "_corrupt_record IS NULL",
        },
        "drop_rules": {},
        "fail_rules": {},
    },

    "customers": {
        "warn_rules": {
            "valid_customer_id": "customer_id IS NOT NULL",
            "valid_customer_unique_id": "customer_unique_id IS NOT NULL",
            "no_corrupt_records": "_corrupt_record IS NULL",
        },
        "drop_rules": {},
        "fail_rules": {},
    },

    "products": {
        "warn_rules": {
            "valid_product_id": "product_id IS NOT NULL",
            "no_corrupt_records": "_corrupt_record IS NULL",
        },
        "drop_rules": {},
        "fail_rules": {},
    },

    "sellers": {
        "warn_rules": {
            "valid_seller_id": "seller_id IS NOT NULL",
            "no_corrupt_records": "_corrupt_record IS NULL",
        },
        "drop_rules": {},
        "fail_rules": {},
    },

    "order_reviews": {
        "warn_rules": {
            "valid_review_id": "review_id IS NOT NULL",
            "valid_order_id": "order_id IS NOT NULL",
            "no_corrupt_records": "_corrupt_record IS NULL",
        },
        "drop_rules": {},
        "fail_rules": {},
    },

    "order_payments": {
        "warn_rules": {
            "valid_order_id": "order_id IS NOT NULL",
            "no_corrupt_records": "_corrupt_record IS NULL",
        },
        "drop_rules": {},
        "fail_rules": {},
    },

    "order_items": {
        "warn_rules": {
            "valid_order_id": "order_id IS NOT NULL",
            "valid_product_id": "product_id IS NOT NULL",
            "valid_seller_id": "seller_id IS NOT NULL",
            "no_corrupt_records": "_corrupt_record IS NULL",
        },
        "drop_rules": {},
        "fail_rules": {},
    },

    "geolocation": {
        "warn_rules": {
            "valid_zip_code_prefix": "geolocation_zip_code_prefix IS NOT NULL",
            "no_corrupt_records": "_corrupt_record IS NULL",
        },
        "drop_rules": {},
        "fail_rules": {},
    },

    "product_category_name_translation": {
        "warn_rules": {
            "valid_category_name": "product_category_name IS NOT NULL",
            "valid_english_category_name": "product_category_name_english IS NOT NULL",
            "no_corrupt_records": "_corrupt_record IS NULL",
        },
        "drop_rules": {},
        "fail_rules": {},
    },
}

def register_bronze_table(table_name):

    source = SOURCE_CONFIG[table_name]
    schema = BRONZE_SCHEMAS[table_name]
    rules = BRONZE_QUALITY_RULES.get(table_name, {})

    dataset_name = f"bronze_{table_name}"

    @dp.materialized_view(
        name=dataset_name,
        comment=f"Raw ingestion of Olist {table_name} from CSV."
    )
    @dp.expect_all(rules.get("warn_rules", {}))
    @dp.expect_all_or_drop(rules.get("drop_rules", {}))
    @dp.expect_all_or_fail(rules.get("fail_rules", {}))
    def ingest():

        return (
            spark.read
            .format("csv")
            .option("header", "true")
            .option("multiLine", "true")
            .option("quote", '"')
            .option("escape", '"')
            .option("mode", "PERMISSIVE")
            .option("columnNameOfCorruptRecord", "_corrupt_record")
            .load(f"{BASE_PATH}/{source['file']}", schema=schema)
            .select(
                "*",
                F.col("_metadata.file_path").alias("source_file")
            )
        )

for table_name in SOURCE_CONFIG:
    register_bronze_table(table_name)

from airflow import DAG
from airflow.providers.google.cloud.operators.bigquery import BigQueryInsertJobOperator
import pendulum
from datetime import timedelta

PROJECT_ID = "woongjin-kdt"  
DATASET = "ga4_daily_funnel_2"       
TABLE = "mart_daily_conversion_2"

default_args = {
    'owner': 'suheon99',
    'retries': 5,
    'retry_delay': timedelta(minutes=5),
    'email': ['yutngjs@gmail.com'],
    'email_on_failure': True
}

with DAG(
    dag_id='mart_daily_conversion_dag',
    default_args=default_args,
    schedule='0 7 * * *',  # 매일 오전 7시
    start_date=pendulum.now().subtract(days=1),
    catchup=False
) as dag:

    create_mart_table = BigQueryInsertJobOperator(
        task_id='create_mart_table',
        gcp_conn_id='my_gcp_conn',
        project_id=PROJECT_ID,
        configuration={
            "query": {
                "query": """
                    CREATE OR REPLACE TABLE `{project}.{dataset}.{table}` AS
                    WITH funnel_counts AS (
                        SELECT
                            PARSE_DATE('%Y%m%d', event_date) AS date,
                            COUNTIF(event_name = 'session_start') AS total_sessions,
                            COUNTIF(event_name = 'view_item') AS product_views,
                            COUNTIF(event_name = 'add_to_cart') AS cart_adds,
                            COUNTIF(event_name = 'begin_checkout') AS checkout_starts,
                            COUNTIF(event_name = 'purchase') AS payments_complete
                        FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
                        GROUP BY date
                    )
                    SELECT
                        date,
                        total_sessions,
                        product_views,
                        cart_adds,
                        checkout_starts,
                        payments_complete,
                        SAFE_DIVIDE(cart_adds, product_views) AS view_to_cart_rate,
                        SAFE_DIVIDE(checkout_starts, cart_adds) AS cart_to_checkout_rate,
                        SAFE_DIVIDE(payments_complete, checkout_starts) AS checkout_to_payment_rate
                    FROM funnel_counts
                    ORDER BY date;
                """.format(project=PROJECT_ID, dataset=DATASET, table=TABLE),
                "useLegacySql": False
            }
        }
    )
![](start_date = datetime(2025, 1, 14).png)

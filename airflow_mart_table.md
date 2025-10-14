# GA4 데이터 Daily Conversion Mart 구축 DAG


### [1] 프로젝트 개요 (Overview)

BigQuery GA4 테이블을 사용하여 각 퍼널별 전환수와 전환율을 계산하고, mart(가공) 데이터를 적재하여 테이블 구축하기


이 DAG는 BigQuery에 적재된 GA4의 이벤트 데이터 기반으로, 최종적으로 purchase 이벤트를 기준으로 전환율(Conversion Rate)과 같은 핵심 지표를 집계한다.
**mart_daily_conversion** 테이블에 매일 적재됨. 





 
### [2] DAG 상세 정보 (Dag Details)
- [ ] Dag ID : 'mart_daily_conversion_dag'
  - DAG의 고유 식별자.
- [ ] Schedule(실행주기) : 0 7 * * *
  - 매일 오전 7시(UTC)에 실행될 것.
  - 실패 시 5분 간격으로 최대 5번 재시도
- [ ] Catchup : False **시작일 이후 실행되지 않은 과거 DAG는 재실행하지 않음.**






---

* 요구 조건
1. BigQueryOperator(BigQueryInsertJobOperator)를 사용한다.
2. 마트 테이블 먼저 생성 후, 데이터 적재
3. GA4의 event 데이터를 참고하여 conversion을 구하는 SQL 쿼리 작성
4. 쿼리 실행 결과는 타겟 테이블 스키마 구조에 맞게 적재할 것 (이때 데이터 타입 유의)
5. 데이터 적재 실패 시 이메일 alert 서비스 설정

## GA4 이벤트 데이터 참고

| Event Name | Event Count |
|-----------|-------------|
| `page_view` | 132,803 |
| `session_start` | 31,668 |
| `user_engagement` | 116,600 |
| `first_visit` | 21,891 |
| `scroll` | 51,449 |
| `view_search_results` | 2,501 |
| `view_item` | 43,708 |
| `add_shipping_info` | 2,412 |
| `view_promotion` | 18,800 |
| `add_payment_info` | 1,586 |
| `select_promotion` | 941 |
| `click` | 107 |
| `begin_checkout` | 4,749 |
| `add_to_cart` | 8,945 |
| `select_item` | 4,928 |
| `purchase` | 614 |
| `view_item_list` | 4 |



--- 

### [3] 사용 기술 및 라이브러리 (Tech Stack) 

   * Orchestration: Apache Airflow
   * Data Warehouse: Google BigQuery
   * Airflow Provider: airflow.providers.google.cloud.operators.bigquery
       * Operator: BigQueryInsertJobOperator
   * Language: Python, SQL


### [4] 작업 순서 (WorkFlow)

  이 DAG는 단일 태스크로 구성되어 있지만, 그 안의 SQL 쿼리가 모든 데이터 변환 및 적재 로직을 수행하는 
  핵심적인 역할을 합니다.

  Task: `create_mart_table`

   * Operator: BigQueryInsertJobOperator
   * 기능: BigQuery에서 SQL 쿼리를 직접 실행하여 데이터 마트를 생성하고 데이터를 삽입합니다.
   * 실행 정책:
       * create_disposition='CREATE_IF_NEEDED': 대상 테이블이 없으면 새로 생성합니다.
       * write_disposition='WRITE_TRUNCATE': 매일 실행 시, 기존 테이블 데이터를 모두 삭제하고 새로운 
         데이터로 덮어씁니다. (멱등성 보장)
   * 대상 테이블: {your_project_id}.mart.daily_conversion
       * 참고: `{your_project_id}` 부분은 실제 GCP 프로젝트 ID로 변경해야 합니다.

  5. 데이터 변환 로직 (SQL Query Analysis)

  아래 SQL 쿼리는 이 DAG의 핵심 로직으로, 총 3개의 CTE(Common Table Expressions)를 거쳐 최종 데이터를 
  만듭니다.

    1 WITH events AS (
    2     -- 1. 이벤트 데이터 정제
    3     SELECT
    4         PARSE_DATE('%Y%m%d', event_date) AS event_date,
    5         event_name,
    6         (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS 
      ga_session_id,
    7         user_pseudo_id
    8     FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
    9     WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20201130'
   10 ),
   11 user_properties AS (
   12     -- 2. 사용자 속성 정보 추출
   13     SELECT
   14         user_pseudo_id,
   15         (SELECT value.string_value FROM UNNEST(user_properties) WHERE key = 'country') AS 
      country,
   16         (SELECT value.string_value FROM UNNEST(user_properties) WHERE key = 'region') AS 
      region
   17     FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
   18     WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20201130'
   19     QUALIFY ROW_NUMBER() OVER (PARTITION BY user_pseudo_id ORDER BY event_timestamp DESC) =
      1
   20 ),
   21 joined_events AS (
   22     -- 3. 이벤트 데이터와 사용자 속성 조인
   23     SELECT
   24         e.*,
   25         p.country,
   26         p.region
   27     FROM events e
   28     LEFT JOIN user_properties p ON e.user_pseudo_id = p.user_pseudo_id
   29 )
   30 -- 4. 최종 데이터 집계 및 전환율 계산
   31 SELECT
   32     event_date,
   33     event_name,
   34     country,
   35     region,
   36     ga_session_id,
   37     COUNT(DISTINCT j.user_pseudo_id) AS user_count,
   38     COUNT(j.ga_session_id) AS session_count,
   39     SUM(CASE WHEN event_name = 'purchase' THEN 1 ELSE 0 END) AS conversion_count,
   40     SAFE_DIVIDE(SUM(CASE WHEN event_name = 'purchase' THEN 1 ELSE 0 END), COUNT
      (j.ga_session_id)) AS conversion_rate
   41 FROM joined_events j
   42 GROUP BY 1, 2, 3, 4, 5

  SQL 로직 상세 분석

   1. `events` CTE:
       * GA4 이벤트 테이블(events_*)에서 날짜, 이벤트 이름, 세션 ID, 사용자 ID를 추출합니다.
       * UNNEST 함수를 사용하여 중첩된 event_params 구조에서 ga_session_id 키의 값을 가져옵니다.

   2. `user_properties` CTE:
       * 사용자별 최신 인구 통계 정보(국가, 지역)를 추출합니다.
       * QUALIFY ROW_NUMBER() ... = 1 구문을 사용하여 사용자(user_pseudo_id)별로 가장 마지막 이벤트의 
         속성만 남겨 데이터 중복을 방지합니다.

   3. `joined_events` CTE:
       * events와 user_properties를 user_pseudo_id 기준으로 LEFT JOIN하여 이벤트 데이터에 사용자 정보를 
         결합합니다.

   4. 최종 `SELECT`:
       * 날짜, 이벤트, 국가, 지역, 세션 ID별로 데이터를 그룹화(GROUP BY)합니다.
       * 각 그룹별로 사용자 수(user_count), 세션 수(session_count), 전환 수(conversion_count)를 
         계산합니다.
       * SAFE_DIVIDE 함수를 사용하여 '0으로 나누기' 오류를 방지하며 전환율(conversion_rate)을 안전하게 
         계산합니다.

  6. 결론 및 의의

  이 DAG는 Airflow의 BigQueryInsertJobOperator와 강력한 SQL 데이터 변환 기능을 활용하여, 복잡한 GA4 
  원시 데이터를 비즈니스 친화적인 데이터 마트로 자동 변환하는 파이프라인입니다.

  매일 자동으로 실행되므로 데이터 분석가와 마케터는 항상 최신 데이터를 기반으로 신속하게 인사이트를 
  얻고 의사결정을 내릴 수 있습니다. 이는 데이터 기반 문화의 핵심적인 부분을 자동화했다는 점에서 큰 
  의의를 가집니다.

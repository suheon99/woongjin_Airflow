#  GA4 Mart Data Pipeline 구축 DAG

---

##  1. 프로젝트 개요 (Overview)

**목표:**  
BigQuery에 적재된 GA4 이벤트 데이터를 기반으로 각 퍼널별 전환수 및 전환율을 계산하고,  
이를 매일 자동으로 `mart_daily_conversion` 테이블에 적재하는 데이터 마트 파이프라인을 구축한다.

이 DAG는 GA4 원시 이벤트 데이터를 정제하여 `purchase`(구매) 이벤트를 기준으로  
전환율(Conversion Rate)과 같은 핵심 지표를 집계한다.  
매일 오전 7시(UTC)에 실행되며, 실패 시 자동 재시도 및 이메일 알림이 설정되어 있다.

---

##  2. DAG 상세 정보 (DAG Details)

| 항목 | 내용 |
|------|------|
| **DAG ID** | `mart_daily_conversion_dag` |
| **스케줄 주기** | `0 7 * * *` (매일 오전 7시 UTC) |
| **Catchup** | `False` (과거 DAG 미실행) |
| **Retry 정책** | 실패 시 5분 간격으로 최대 5회 재시도 |
| **Owner** | `suheon99` |
| **이메일 알림** | `yutngjs@gmail.com` |

---

##  3. 요구 조건 (Requirements)

1. **BigQueryInsertJobOperator** 사용  
2. **Mart 테이블 생성 후 데이터 적재**  
3. **GA4 이벤트 데이터 기반 전환 계산 SQL 작성**  
4. **타깃 테이블 스키마에 맞는 데이터 타입 유지**  
5. **데이터 적재 실패 시 이메일 알림 설정**

---

##  4. 참고 데이터 (GA4 이벤트 데이터 예시)

| Event Name | Event Count |
|-------------|-------------|
| `page_view` | 132,803 |
| `session_start` | 31,668 |
| `user_engagement` | 116,600 |
| `first_visit` | 21,891 |
| `scroll` | 51,449 |
| `view_item` | 43,708 |
| `add_to_cart` | 8,945 |
| `begin_checkout` | 4,749 |
| `purchase` | 614 |
| ... | ... |

> 참고: `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`

---

##  5. 사용 기술 및 라이브러리 (Tech Stack)

| 구분 | 사용 기술 |
|------|-------------|
| **Orchestration** | Apache Airflow |
| **Data Warehouse** | Google BigQuery |
| **Airflow Provider** | `airflow.providers.google.cloud` |
| **Operator** | `BigQueryInsertJobOperator` |
| **Language** | Python, SQL |

---
##  6. 작업 순서 (Workflow)

이 DAG는 단일 Task(`create_mart_table`)로 구성되어 있으며,  
그 안의 SQL 쿼리가 데이터 변환 및 적재 로직을 모두 수행함.

| 구성 요소 | 설명 |
|------------|------|
| **Task Name** | `create_mart_table` |
| **Operator** | `BigQueryInsertJobOperator` |
| **기능** | BigQuery에서 SQL 쿼리를 실행하여 데이터 마트를 생성하고 데이터를 적재함 |
| **create_disposition** | `'CREATE_IF_NEEDED'` → 테이블이 존재하지 않으면 새로 생성 |
| **write_disposition** | `'WRITE_TRUNCATE'` → 매일 실행 시 기존 데이터를 덮어써 멱등성 보장 |
| **대상 테이블** | `ga4_daily.mart_daily_conversion` |

```
DAG: mart_daily_conversion_dag
└── Task: create_mart_table
├── Run SQL in BigQuery
├── Create mart table if not exists
├── Replace existing data with new daily results
└── Store results in ga4_daily.mart_daily_conversion
```

---

## 7. 데이터 변환 로직 (SQL Query)


```
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
```

## 8. 파이프라인 구조 요약

```
GA4 Raw Data (events_*)
      ↓
SQL Transform (전환율 계산)
      ↓
BigQuery Mart Table (mart_daily_conversion)
      ↓
Airflow DAG 자동 실행 (매일 오전 7시)
```

## 9. 결과 및 의의 (Conclusion)
이 DAG는 **Airflow와 BigQuery**의 강력한 결합을 통해
GA4 원시 데이터를 자동으로 전처리·집계하여
비즈니스 분석용 Mart 테이블을 매일 생성.

이를 통해 분석가와 마케터는
항상 최신 데이터를 기반으로 빠르고 정확한 인사이트를 얻을 수 있으며,
데이터 파이프라인의 자동화와 멱등성을 동시에 달성했다는 점에서 의의가 있음.

---

## 10. 구현 순서 (Implementation Steps)
1. **SQL 쿼리 작성 및 테스트**
   - BigQuery에서 SQL 쿼리를 작성하고 결과 검증

2. **타겟 테이블 생성**
   - 본인의 프로젝트 > 데이터셋 > 빈 타겟 테이블 생성

3. **Airflow DAG 생성 및 테스트**
   - DAG 파일 작성 및 로컬/스테이징 환경에서 테스트

4. **코드 푸시 및 문서화**
   - 완성된 코드를 본인 폴더에 푸시
   - 테이블 적재 완료 스크린샷을 마크다운에 첨부
   - 참고: [VSCode Paste Image Extension](https://marketplace.cursorapi.com/items/?itemName=mushan.vscode-paste-image)

---
## 🗂️ 예시 파일 구조
```
📦 airflow-dags/
 ┣ 📜 mart_daily_conversion_dag.py
 ┣ 📜 README.md
 ┗ 📂 logs/
```

--- 
✅ 마무리 한 줄 요약
“GA4 데이터를 기반으로 매일 자동 전환율 마트를 생성하는 Airflow + BigQuery 기반 데이터 파이프라인.”



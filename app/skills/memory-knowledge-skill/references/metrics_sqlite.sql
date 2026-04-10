-- System Memory KPI SQL Draft (SQLite)
-- Date anchor: 2026-04-10

-- ========================================
-- A. Process KPIs (monthly)
-- ========================================

-- A1. Trigger Hit Rate = hit triggers / all triggers
WITH trigger_m AS (
  SELECT
    strftime('%Y-%m', event_time) AS month,
    COUNT(*) AS trigger_cnt
  FROM memory_trigger_event
  GROUP BY 1
),
hit_m AS (
  SELECT
    strftime('%Y-%m', t.event_time) AS month,
    COUNT(DISTINCT t.event_id) AS hit_trigger_cnt
  FROM memory_trigger_event t
  JOIN memory_retrieval_event r
    ON r.trigger_event_id = t.event_id
  GROUP BY 1
)
SELECT
  tm.month,
  tm.trigger_cnt,
  COALESCE(hm.hit_trigger_cnt, 0) AS hit_trigger_cnt,
  ROUND(COALESCE(hm.hit_trigger_cnt, 0) * 1.0 / NULLIF(tm.trigger_cnt, 0), 4) AS trigger_hit_rate
FROM trigger_m tm
LEFT JOIN hit_m hm ON hm.month = tm.month
ORDER BY tm.month;

-- A2. Adoption Rate = accepted decisions / retrieval rows
WITH m AS (
  SELECT
    strftime('%Y-%m', r.event_time) AS month,
    COUNT(*) AS retrieved_cnt,
    SUM(CASE WHEN d.decision = 'accepted' THEN 1 ELSE 0 END) AS accepted_cnt
  FROM memory_retrieval_event r
  LEFT JOIN memory_decision_event d
    ON d.trigger_event_id = r.trigger_event_id
   AND d.memory_id = r.memory_id
  GROUP BY 1
)
SELECT
  month,
  retrieved_cnt,
  accepted_cnt,
  ROUND(accepted_cnt * 1.0 / NULLIF(retrieved_cnt, 0), 4) AS adoption_rate
FROM m
ORDER BY month;

-- A3. Noise Rate = irrelevant decisions / all decisions
SELECT
  strftime('%Y-%m', event_time) AS month,
  COUNT(*) AS decision_cnt,
  SUM(CASE WHEN decision = 'irrelevant' THEN 1 ELSE 0 END) AS irrelevant_cnt,
  ROUND(SUM(CASE WHEN decision = 'irrelevant' THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(*), 0), 4) AS noise_rate
FROM memory_decision_event
GROUP BY 1
ORDER BY 1;

-- A4. Freshness Rate (need memory_card table)
-- expected table: memory_card(id, status, created_at, last_reviewed_at)
SELECT
  date('now') AS snapshot_date,
  SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_cnt,
  SUM(
    CASE
      WHEN status = 'active' AND date(COALESCE(last_reviewed_at, created_at)) >= date('now', '-90 day') THEN 1
      ELSE 0
    END
  ) AS fresh_active_cnt,
  ROUND(
    SUM(
      CASE
        WHEN status = 'active' AND date(COALESCE(last_reviewed_at, created_at)) >= date('now', '-90 day') THEN 1
        ELSE 0
      END
    ) * 1.0 / NULLIF(SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END), 0),
    4
  ) AS freshness_rate_90d
FROM memory_card;

-- ========================================
-- B. Governance Alerts
-- ========================================

-- B1. Expired but still active cards
-- expected table: memory_card(id, title, owner_team, status, expire_at)
SELECT id, title, owner_team, expire_at
FROM memory_card
WHERE status = 'active'
  AND date(expire_at) < date('now')
ORDER BY date(expire_at) ASC;

-- B2. Low-value cards: 2 consecutive months low adoption + high noise
WITH monthly AS (
  SELECT
    memory_id,
    strftime('%Y-%m', event_time) AS month,
    COUNT(*) AS decision_cnt,
    SUM(CASE WHEN decision = 'accepted' THEN 1 ELSE 0 END) AS accepted_cnt,
    SUM(CASE WHEN decision = 'irrelevant' THEN 1 ELSE 0 END) AS irrelevant_cnt,
    ROUND(SUM(CASE WHEN decision = 'accepted' THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(*), 0), 4) AS adoption_rate,
    ROUND(SUM(CASE WHEN decision = 'irrelevant' THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(*), 0), 4) AS noise_rate
  FROM memory_decision_event
  GROUP BY 1, 2
),
flagged AS (
  SELECT *
  FROM monthly
  WHERE adoption_rate < 0.10
    AND noise_rate > 0.40
)
SELECT f1.memory_id, f1.month AS month_1, f2.month AS month_2
FROM flagged f1
JOIN flagged f2
  ON f2.memory_id = f1.memory_id
 AND date(f2.month || '-01') = date(f1.month || '-01', '+1 month')
ORDER BY f1.memory_id, f1.month;

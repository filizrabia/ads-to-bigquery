-- Campaign performance with week-over-week change, for reporting.
with weekly as (
    select
        date_trunc(date, isoweek) as week,
        platform,
        campaign_id,
        any_value(campaign_name) as campaign_name,
        any_value(campaign_objective) as campaign_objective,
        sum(spend) as spend,
        sum(conversions) as conversions,
        sum(conversion_value) as conversion_value
    from {{ ref('stg_ads__daily') }}
    group by 1, 2, 3
)

select
    *,
    safe_divide(conversion_value, spend) as roas,
    safe_divide(spend, conversions) as cpa,
    safe_divide(
        spend - lag(spend) over (partition by platform, campaign_id order by week),
        lag(spend) over (partition by platform, campaign_id order by week)
    ) as spend_wow_change
from weekly

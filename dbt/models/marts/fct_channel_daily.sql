-- Daily totals per platform: the table MMM and dashboards read from.
select
    date,
    platform,
    sum(impressions) as impressions,
    sum(clicks) as clicks,
    sum(spend) as spend,
    sum(conversions) as conversions,
    sum(conversion_value) as conversion_value,
    safe_divide(sum(clicks), sum(impressions)) as ctr,
    safe_divide(sum(spend), sum(clicks)) as cpc,
    safe_divide(sum(spend), sum(conversions)) as cpa,
    safe_divide(sum(conversion_value), sum(spend)) as roas
from {{ ref('stg_ads__daily') }}
group by 1, 2

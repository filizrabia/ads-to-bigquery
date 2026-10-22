-- Light cleanup on top of the raw table: types, naming, and derived flags.
select
    date,
    platform,
    account_id,
    campaign_id,
    campaign_name,
    ad_group_id,
    ad_group_name,
    impressions,
    clicks,
    cast(spend as float64) as spend,
    conversions,
    cast(conversion_value as float64) as conversion_value,
    currency,
    -- Campaign naming convention: "<objective> | <detail>"
    lower(trim(split(campaign_name, '|')[safe_offset(0)])) as campaign_objective
from {{ source('raw', 'ads_daily') }}

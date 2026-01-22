# KEY FORMAT INCONSISTENCY ISSUE

## The Problem

There are TWO different key formats being used:

### Format 1: Data Context Key (3 parts)
Used by: Planner, Fetcher, `analyses_required` dict, `kline_data` dict
```
{symbol}|{timeframe}|{start_datetime}:{end_datetime}
Example: "BEL.NS|5m|2026-01-19T09:15:00+05:30:2026-01-19T15:30:00+05:30"
```

### Format 2: Analysis Store Key (4 parts)  
Used by: Analysis agents storage, `analysis_store` dict
```
{symbol}|{timeframe}|{start_datetime}:{end_datetime}|{horizon}
Example: "BEL.NS|5m|2026-01-19T09:15:00+05:30:2026-01-19T15:30:00+05:30|intraday"
```

## The Flow

1. **Planner** creates `analyses_required` with 3-part keys
2. **Fetcher** uses 3-part keys to fetch data into `kline_data`
3. **Indicator Agent** reads from `kline_data` using 3-part key ✅
4. **Indicator Agent** stores to `analysis_store` using 4-part key ✅
5. **Dialogue Agent** filters `analysis_store` by constructing 4-part key from `analyses_required` ✅

## Why Indicator Analysis Isn't Showing

The flow SHOULD work, but let me check if dialogue agent is constructing the right key...

The issue is in `get_filtered_analysis_store()` - it reads `analyses_required` (3-part keys) and constructs 4-part keys by adding horizon from the spec.

## Why Decision Shows HOLD 0%

Decision agent likely can't find indicator/pattern/trend results because of key mismatch or missing data.

## Why record.csv isn't created

The `generate_kline_image` function is only called by pattern agent, not automatically. If pattern agent fails or isn't called, record.csv won't be created.

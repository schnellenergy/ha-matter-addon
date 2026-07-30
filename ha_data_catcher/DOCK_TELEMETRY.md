# Dock Telemetry — the dock's own counters, from firmware to BigQuery

This document covers **dock-side telemetry**: the press and encoder counters the
dock hardware keeps internally, how the HA Data Catcher add-on reads them
straight off the Matter Server, and how they reach BigQuery.

> **This pipeline replaced a Google Sheet.** Until v1.1.0, `dock_logs` was a
> native BigQuery table that an Apps Script inside a Google Sheet replaced
> wholesale on every edit, and the counters were typed in by hand. The counters
> are now read from the hardware automatically. See
> [§8 Migration](#8-migration-from-the-google-sheet-pipeline) for the cutover,
> and [§4 Schema](#4-schema) for what changed in the columns.

Related: `APP_TELEMETRY.md` (app-side pipeline), `HA_TELEMETRY.md` (hub-side
event pipeline), `Analytics/Schnell_Analytics_Architecture.md` (full analytics
architecture) — all in the Analytics repo.

---

## 1. What dock telemetry is

A dock is a physical button panel; each button ("docklet") controls a device.
The dock firmware keeps its **own internal counters** — how many times each
docklet was pressed, how many of those presses succeeded, and the same pair for
the rotary encoder (dim up/down).

Four counters per docklet, exposed as Matter attributes:

| Attribute | Meaning |
|---|---|
| `2` (`0x0002`) | **Total press count** — every press registered by the docklet |
| `3` (`0x0003`) | **Successful press count** — presses that completed successfully |
| `4` (`0x0004`) | **Total encoder count** — every increment/decrement (dim) action |
| `5` (`0x0005`) | **Successful encoder count** — encoder actions that completed successfully |

Failures are the difference: `total − success`. Attributes `0` and `1` on the
same cluster are unused by the current firmware and are not collected.

How this differs from the other two pipelines:

- **`app_logs`** sees a dock press only if the app is open to observe it.
- **`ha_logs`** sees the press itself (a `call_service` tagged with `dock_id`)
  and the state change it caused, 24/7 — **this remains the source of dock
  reliability on the dashboard.**
- **`dock_logs`** is what the dock hardware itself counted. It sees presses that
  never reached Home Assistant at all, which is exactly what makes it valuable:
  a press counted by the firmware with no corresponding `ha_logs` row is a real
  failure that no other pipeline can see.

---

## 2. Data flow

```
Dock firmware counters  (vendor cluster 0xFFF1FC21, attributes 2-5, endpoints 1-6)
      │
      │  ws://core-matter-server:5580/ws
      │    · start_listening  → node dump + attribute_updated event stream  (push)
      │    · read_attribute   → live device read every 15 min               (poll)
      ▼
HA Data Catcher add-on
      │  matter_collector.py    identifies docks, extracts counter snapshots
      │  dock_telemetry.py      deltas, reset detection, debounce, identity resolution
      ▼
Firestore   smash_db/<hub_mac>/dock_events/<record_id>
      │  Stream Firestore to BigQuery extension
      ▼
BigQuery    schnell_analytics.dock_logs_raw_changelog     (raw, extension-managed)
            schnell_analytics.dock_logs                   (flattened view — primary)
            schnell_analytics.dock_logs_action_daily      (compatibility view)
```

### Why two update paths

The add-on runs push and poll **at the same time**, on purpose:

- **Push** (`attribute_updated` events) is instant and free, but the Matter
  Server only emits it for attributes it holds a subscription on. If the
  firmware does not report on the vendor cluster, push never fires.
- **Poll** (`read_attribute`) is a **live device read**, not a cache read. It
  works regardless of what the firmware reports, which makes it the guaranteed
  path. Default interval 900 s, plus one read immediately on connect.

Whichever arrives first wins; the delta logic makes duplicates harmless.
Check the `source` column to see which path produced a row.

---

## 3. How a dock is identified

**The node** — a Matter node is treated as a dock when its ProductName (Basic
Information cluster `40`, attribute `3`) starts with a configured prefix,
`Dock_` by default. That matches `Dock_6D`, and `Dock_4D` when it ships.

**The cluster** — the counters live on a manufacturer-specific Matter cluster.
Resolution order:

1. The `dock_cluster_id` option (default `4294048801` = `0xFFF1FC21`), if that
   cluster is actually present on the node.
2. Otherwise **auto-detect**: any cluster in the Matter manufacturer-extensible
   range (`cluster & 0xFFFF >= 0xFC00`) carrying counter attributes on
   endpoints 1–6, preferring whichever appears on the most endpoints.
3. Neither → the node is skipped and its actual cluster IDs are logged.

Auto-detection is not paranoia. Manufacturer cluster IDs are
`(vendor_id << 16) | 0xFCxx`, and `0xFFF1FC21` uses `0xFFF1` — the **Matter test
vendor ID**. The day firmware ships with a real Schnell vendor ID, the cluster
ID changes. A hardcoded constant would silently read zeros forever; the
`cluster_id` column on every row makes such a change visible in the data.

**The dock's name** — the Matter Server only knows numeric node IDs, so names
come from the Custom Data Storage add-on. That store is schema-less (it persists
whatever the mobile app writes) and the shape has varied between app versions,
so resolution is deliberately tolerant:

| Row field | Resolved from (first match wins) |
|---|---|
| `dock_id` | the entry's own `dock_id`, else the `docks` map key |
| `dock_name` | `label` → `name` → `dock_name` → `title` |
| `room`, `floor` | `room_id` / `roomId` → `home_setup` rooms and floors |
| `docklet_id` | `entity_id` → `entityId` → `bound_device_entity_id` → the docklet key |
| `docklet_label` | `bound_device_label` → `boundDeviceLabel` → `label` → `name` |

The docklet for an endpoint is located by `position`, `endpoint_id`,
`endpointId`, `endpoint`, `index`, or `slot` — whichever the app used — then by
list order, then by the numeric suffix of the key (`docklet_1` → 1). Both a
keyed map and a plain list are handled, under `docklets`, `sub_devices`,
`buttons`, `slots`, or `endpoints`.

An unbound docklet stores the literal `not_mapped`, which is treated as empty:
`docklet_id` still populates from the entity ID, and `docklet_label` stays blank
until a device is actually bound in the app. No name is invented.

### Linking the node when `matter_node_id` is missing

The app has shipped builds that save a dock's `matter_node_id` as `null` (snaps
are unaffected — it is specific to the dock commissioning path). Without a
fallback, every such dock would produce permanently nameless rows, and fixing it
would mean re-commissioning already-deployed hardware. So the node is matched in
three escalating steps:

1. **The entry's own node ID** — `matter_node_id`, `matterNodeId`, `node_id`, or
   `nodeId`; exact match first, then numeric suffix, so `20` / `node_20` / `1-20`
   all match (the same logic `ha_logs` uses). An `entity_id` of `node_20` also
   counts.
2. **Home Assistant's device registry.** The app does record each docklet's own
   entity ID (`light.dock_6d_light_1`), and HA's device registry knows which
   Matter node that entity belongs to. Resolving through it identifies the dock
   with no help from the app. Only the docklet's *own* `entity_id` is used —
   never `bound_device_entity_id`, which points at the controlled device on a
   completely different node.
3. **Sole-dock pairing.** If Custom Storage holds exactly one dock with no node
   ID, and exactly one dock is present on the Matter fabric, the mapping is
   unambiguous and they are paired.

Each fallback logs once, saying which path was used and that fixing
`matter_node_id` in the app would make it direct. Guardrails: an entry that
names a *different* node is never hijacked by a fallback, and with more dock
nodes than storage entries the add-on leaves the fields empty rather than risk
attaching counters to the wrong dock.

A node with no Custom Storage entry at all **still gets its counters recorded**,
with identity fields empty and a warning listing exactly what the store does
hold. Counters are the valuable part, and the next observation picks up the name
once the app has saved the dock.

---

## 4. Schema

### 4.1 Cumulative vs delta — read this before writing a query

The firmware counters are **cumulative**: totals since the dock last booted, not
per-press events. So each row carries both:

- `*_count` — the **absolute** counter as the device reported it. Ground truth.
- `*_delta` — the change **since the previous row** for that dock + endpoint.

**Use the deltas for "how many presses today"** (`SUM(press_total_delta)`).
Summing a cumulative column is meaningless. The deltas are what make this table
aggregate the way the old Sheet-based table did.

Two behaviours worth knowing:

- **Counter reset.** A dock power-cycle restarts the counters at zero. That is
  detected (a counter went *down*), `counter_reset` is set `true`, and the delta
  is the new value rather than a negative number.
- **Self-healing writes.** If a Firestore write fails, the add-on does not
  advance its saved totals, so the next row's delta includes the presses from
  the failed one. Nothing is lost or double-counted.

### 4.2 Columns (`dock_logs` view)

| Field | Type | Meaning |
|---|---|---|
| `hub_id` | STRING | Hub MAC — join key to `ha_logs.hub_id` / `app_logs.hub_id` |
| `record_id` | STRING | `<node_id>-<endpoint>-<unix_ms>`, unique per row |
| `timestamp` | TIMESTAMP | When the add-on observed the counters (hub-local tz) |
| `date` | STRING (YYYY-MM-DD) | Observation date |
| `time` | STRING (HH:MM:SS) | Observation time |
| `hour` | INT64 | Hour of day, 0–23 |
| `day_of_week` | STRING | e.g. "Monday" |
| `matter_node_id` | STRING | Matter node ID (e.g. `20`) |
| `dock_id` | STRING | Physical dock ID from Custom Storage |
| `dock_name` | STRING | Dock label, e.g. "Living Room Dock" |
| `room`, `floor` | STRING | Resolved location |
| `endpoint` | INT64 | Docklet position on the dock, 1–6 |
| `docklet_id` | STRING | Docklet entity ID |
| `docklet_label` | STRING | Bound device label |
| `press_total_count` | INT64 | **Attribute 2** — cumulative total presses |
| `press_success_count` | INT64 | **Attribute 3** — cumulative successful presses |
| `encoder_total_count` | INT64 | **Attribute 4** — cumulative encoder actions |
| `encoder_success_count` | INT64 | **Attribute 5** — cumulative successful encoder actions |
| `press_total_delta` | INT64 | Presses since the previous row |
| `press_success_delta` | INT64 | Successful presses since the previous row |
| `encoder_total_delta` | INT64 | Encoder actions since the previous row |
| `encoder_success_delta` | INT64 | Successful encoder actions since the previous row |
| `press_failure_delta` | INT64 | Derived: `press_total_delta − press_success_delta` |
| `encoder_failure_delta` | INT64 | Derived: `encoder_total_delta − encoder_success_delta` |
| `counter_reset` | BOOL | The dock rebooted and restarted its counters at this row |
| `source` | STRING | `push` (firmware reported), `poll` (live read), `baseline` (first sighting) |
| `product_name` | STRING | e.g. `Dock_6D` |
| `cluster_id` | INT64 | Vendor cluster actually read — surfaces a firmware VID change |

Row granularity: **one row per dock × endpoint × change.** An idle dock writes
nothing at all. A single press bumps attributes 2 and 3 within milliseconds; a
2-second debounce window coalesces them into one row rather than two half-filled
ones.

### 4.3 Old schema → new schema

| Old column (Sheet era) | Now |
|---|---|
| `hub_id` | `hub_id` — unchanged |
| `date`, `day_of_week` | unchanged, plus new `timestamp`, `time`, `hour` |
| `dock_id` | unchanged — but now resolved automatically, not typed in |
| `docklet_id` | unchanged — now resolved from the endpoint position |
| `action` (`toggle`/`increment`/`decrement`) | **Removed.** The firmware counts presses and encoder actions, and does not distinguish increment from decrement. The `press`/`encoder` split replaces it, and `dock_logs_action_daily` re-materializes an `action` column for existing queries |
| `total_action_count` | `press_total_delta` / `encoder_total_delta` |
| `success_count` | `press_success_delta` / `encoder_success_delta` |
| `failure_count` | `press_failure_delta` / `encoder_failure_delta` |
| *(none)* | New: absolute `*_count` columns, `dock_name`, `room`, `floor`, `docklet_label`, `endpoint`, `matter_node_id`, `counter_reset`, `source`, `product_name`, `cluster_id` |

**Dashboard impact:** the old `f_dock` query in
`Analytics/analytics-api/main.py` selects `action`, `total_action_count`,
`success_count`, and `failure_count`. Point it at `dock_logs_action_daily`
(§8 step 5) and it keeps working unchanged. `dock_logs` itself is the richer
table to build new panels on.

---

## 5. Add-on configuration

| Option | Default | Description |
|---|---|---|
| `enable_dock_telemetry` | `true` | Master switch. `false` reverts the add-on to pure Home Assistant event collection |
| `matter_server_url` | `ws://core-matter-server:5580/ws` | Matter Server add-on WebSocket |
| `dock_product_names` | `Dock_` | Comma-separated ProductName prefixes that identify a dock |
| `dock_cluster_id` | `4294048801` | Vendor counter cluster. `0` = rely on auto-detection only |
| `dock_endpoints` | `1-6` | Endpoint range to scan. Accepts `1-6` or `1,2,5` |
| `dock_poll_interval` | `900` | Reconciliation live-read interval, seconds (60–86400) |
| `dock_min_write_interval` | `2` | Debounce window, seconds (0–60) |

Dock telemetry is fully isolated from Home Assistant event collection. If the
Matter Server is unreachable, speaks an incompatible protocol, or no dock is
commissioned, `ha_logs` keeps flowing untouched — the add-on logs the reason and
carries on.

---

## 6. Verifying it works

A healthy start looks like this in the add-on log:

```
[App] Dock telemetry enabled — products ['Dock_'], cluster 4294048801, endpoints 1-6
[Matter] Dock telemetry collector starting — server: ws://core-matter-server:5580/ws
[Matter] Connected to Matter Server — schema_version=… sdk_version=…
[Matter] Subscribed to event stream — 7 node(s) reported
[Matter] Dock detected — node 20 ('Dock_6D') cluster 4294048801 (0xFFF1FC21) endpoints [1, 2, 3, 4, 5, 6]
[Matter] Reading baseline counters for 1 dock(s)...
[Dock] Living Room Dock endpoint 1: presses 102 (+0), success 69 (+0), encoder 21 (+0), encoder success 21 (+0) [baseline]
[Firestore] Wrote 1 dock record(s) to Firestore.
```

Then press a docklet a few times and confirm one row appears per press burst:

```
[Dock] Living Room Dock endpoint 1: presses 105 (+3), success 71 (+2), encoder 21 (+0), encoder success 21 (+0)
```

`(+3)` after three presses is the delta doing its job. The baseline rows on
first start are expected: they record the absolute counters without inventing
history for presses that happened before the add-on was watching.

---

## 7. Counter state on the hub

Deltas require knowing the previous totals, so they are persisted to
`/data/dock_counters.json` inside the add-on's data volume:

```json
{"version": 1, "hub_id": "2C:CF:67:6E:11:52",
 "counters": {"20": {"1": {"2": 105, "3": 71, "4": 21, "5": 21}}}}
```

- Written atomically after every successfully written row, so a crash cannot
  corrupt it.
- Survives add-on restarts and hub reboots — a restart continues the delta
  series instead of re-reporting history.
- Deleting it is safe: the next observation of each counter becomes a baseline
  row (absolute values recorded, deltas zero). Only do this if the delta series
  is known to be wrong.

---

## 8. Migration from the Google Sheet pipeline

Run these **in order**. Step 1 before step 2, or the Apps Script will truncate
the table out from under the new pipeline.

### Step 1 — Retire the Sheet sync

Open the "Schnell Dock Data" Sheet → **Extensions → Apps Script → Triggers**
(clock icon) → delete the `onChangeSync` trigger.

Keep the Sheet and `Analytics/dock_sheet_apps_script.gs` as an archive; just
make sure nothing can fire `syncToBigQuery` again. While that trigger lives,
every Sheet edit issues a `WRITE_TRUNCATE` load job against `dock_logs`.

### Step 2 — Drop the old native table

This clears all hand-entered history, as intended. **Irreversible.**

```sql
DROP TABLE `schnell-home-automation.schnell_analytics.dock_logs`;
```

The name must be free before step 4 can create a view with it.

### Step 3 — Install the Firestore→BigQuery extension for dock events

A **second instance** of *Stream Firestore to BigQuery*, alongside the existing
`ha_events` one:

| Setting | Value |
|---|---|
| Collection path | `smash_db/{hubId}/dock_events` |
| Enable collection-group query | **Yes** (scopes every hub automatically) |
| Dataset ID | `schnell_analytics` |
| Table ID | `dock_logs` |
| Dataset location | same as the existing dataset |

It creates `dock_logs_raw_changelog` and `dock_logs_raw_latest`, leaving the
bare name `dock_logs` free for our own view — exactly the arrangement `ha_logs`
already uses.

> **Install this before starting the add-on.** The extension only picks up
> documents written after it is installed. Rows written earlier stay in
> Firestore but never reach BigQuery unless you run the extension's import
> script.

### Step 4 — Create the primary view

Same shape as the existing `ha_logs` view: read the extension's `_raw_latest`
view and flatten the `data` JSON with `SAFE_CAST`, so a malformed value yields
`NULL` instead of failing the whole query.

```sql
CREATE OR REPLACE VIEW `schnell-home-automation.schnell_analytics.dock_logs` AS
SELECT
  JSON_VALUE(data, '$.hub_id')                                          AS hub_id,
  JSON_VALUE(data, '$.record_id')                                       AS record_id,
  SAFE_CAST(JSON_VALUE(data, '$.timestamp') AS TIMESTAMP)               AS timestamp,
  JSON_VALUE(data, '$.date')                                            AS date,
  JSON_VALUE(data, '$.time')                                            AS time,
  SAFE_CAST(JSON_VALUE(data, '$.hour') AS INT64)                        AS hour,
  JSON_VALUE(data, '$.day_of_week')                                     AS day_of_week,
  JSON_VALUE(data, '$.matter_node_id')                                  AS matter_node_id,
  JSON_VALUE(data, '$.dock_id')                                         AS dock_id,
  JSON_VALUE(data, '$.dock_name')                                       AS dock_name,
  JSON_VALUE(data, '$.room')                                            AS room,
  JSON_VALUE(data, '$.floor')                                           AS floor,
  SAFE_CAST(JSON_VALUE(data, '$.endpoint') AS INT64)                    AS endpoint,
  JSON_VALUE(data, '$.docklet_id')                                      AS docklet_id,
  JSON_VALUE(data, '$.docklet_label')                                   AS docklet_label,
  SAFE_CAST(JSON_VALUE(data, '$.press_total_count') AS INT64)           AS press_total_count,
  SAFE_CAST(JSON_VALUE(data, '$.press_success_count') AS INT64)         AS press_success_count,
  SAFE_CAST(JSON_VALUE(data, '$.encoder_total_count') AS INT64)         AS encoder_total_count,
  SAFE_CAST(JSON_VALUE(data, '$.encoder_success_count') AS INT64)       AS encoder_success_count,
  SAFE_CAST(JSON_VALUE(data, '$.press_total_delta') AS INT64)           AS press_total_delta,
  SAFE_CAST(JSON_VALUE(data, '$.press_success_delta') AS INT64)         AS press_success_delta,
  SAFE_CAST(JSON_VALUE(data, '$.encoder_total_delta') AS INT64)         AS encoder_total_delta,
  SAFE_CAST(JSON_VALUE(data, '$.encoder_success_delta') AS INT64)       AS encoder_success_delta,
  SAFE_CAST(JSON_VALUE(data, '$.press_total_delta') AS INT64)
    - SAFE_CAST(JSON_VALUE(data, '$.press_success_delta') AS INT64)     AS press_failure_delta,
  SAFE_CAST(JSON_VALUE(data, '$.encoder_total_delta') AS INT64)
    - SAFE_CAST(JSON_VALUE(data, '$.encoder_success_delta') AS INT64)   AS encoder_failure_delta,
  SAFE_CAST(JSON_VALUE(data, '$.counter_reset') AS BOOL)                AS counter_reset,
  JSON_VALUE(data, '$.source')                                          AS source,
  JSON_VALUE(data, '$.product_name')                                    AS product_name,
  SAFE_CAST(JSON_VALUE(data, '$.cluster_id') AS INT64)                  AS cluster_id
FROM `schnell-home-automation.schnell_analytics.dock_logs_raw_latest`
WHERE data IS NOT NULL;
```

> If the extension was configured without the latest-snapshot view, swap the
> `FROM` for the changelog and dedupe by document:
>
> ```sql
> FROM (
>   SELECT data
>   FROM `schnell-home-automation.schnell_analytics.dock_logs_raw_changelog`
>   WHERE operation != 'DELETE'
>   QUALIFY ROW_NUMBER() OVER (PARTITION BY document_id ORDER BY timestamp DESC) = 1
> )
> ```
>
> Dock rows are written once and never updated, so both forms return the same
> data — the dedupe is purely defensive.

### Step 5 — Create the compatibility view

Daily totals in the old nine-column shape, so existing dashboard queries need a
table name change and nothing else:

```sql
CREATE OR REPLACE VIEW `schnell-home-automation.schnell_analytics.dock_logs_action_daily` AS
WITH base AS (
  SELECT * FROM `schnell-home-automation.schnell_analytics.dock_logs`
)
SELECT
  hub_id, date, day_of_week, dock_id, docklet_id,
  'press' AS action,
  SUM(press_total_delta)                            AS total_action_count,
  SUM(press_success_delta)                          AS success_count,
  SUM(press_total_delta - press_success_delta)       AS failure_count
FROM base
GROUP BY hub_id, date, day_of_week, dock_id, docklet_id
HAVING SUM(press_total_delta) > 0

UNION ALL

SELECT
  hub_id, date, day_of_week, dock_id, docklet_id,
  'encoder' AS action,
  SUM(encoder_total_delta)                          AS total_action_count,
  SUM(encoder_success_delta)                        AS success_count,
  SUM(encoder_total_delta - encoder_success_delta)   AS failure_count
FROM base
GROUP BY hub_id, date, day_of_week, dock_id, docklet_id
HAVING SUM(encoder_total_delta) > 0;
```

### Step 6 — Start the add-on and verify

Follow §6, then confirm the row reached BigQuery:

```sql
SELECT timestamp, dock_name, endpoint, docklet_label,
       press_total_count, press_total_delta, source
FROM `schnell-home-automation.schnell_analytics.dock_logs`
ORDER BY timestamp DESC
LIMIT 20;
```

---

## 9. Queries

```sql
-- Presses and reliability per docklet, worst first
SELECT
  dock_name, endpoint, docklet_label,
  SUM(press_total_delta)   AS presses,
  SUM(press_failure_delta) AS failures,
  ROUND(100 * SUM(press_success_delta) / NULLIF(SUM(press_total_delta), 0), 2) AS reliability_pct
FROM `schnell-home-automation.schnell_analytics.dock_logs`
GROUP BY dock_name, endpoint, docklet_label
ORDER BY failures DESC, presses DESC;
```

```sql
-- Daily volume: presses vs encoder actions
SELECT
  date, day_of_week,
  SUM(press_total_delta)   AS presses,
  SUM(encoder_total_delta) AS encoder_actions,
  ROUND(100 * SUM(press_success_delta) / NULLIF(SUM(press_total_delta), 0), 2) AS press_reliability_pct
FROM `schnell-home-automation.schnell_analytics.dock_logs`
GROUP BY date, day_of_week
ORDER BY date;
```

```sql
-- Current absolute counters per docklet (the device's own lifetime totals)
SELECT dock_name, endpoint, docklet_label,
       press_total_count, press_success_count,
       encoder_total_count, encoder_success_count, timestamp
FROM `schnell-home-automation.schnell_analytics.dock_logs`
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY hub_id, dock_id, endpoint ORDER BY timestamp DESC) = 1;
```

```sql
-- Presses the hardware counted but Home Assistant never saw.
-- The whole point of this table: presses that never became an HA command.
SELECT
  d.date,
  SUM(d.press_total_delta) AS hardware_presses,
  (SELECT COUNT(*)
   FROM `schnell-home-automation.schnell_analytics.ha_logs` h
   WHERE h.hub_id = d.hub_id
     AND h.ha_event_type = 'call_service'
     AND h.dock_id IS NOT NULL
     AND h.is_trigger
     AND h.date = d.date) AS ha_observed_presses
FROM `schnell-home-automation.schnell_analytics.dock_logs` d
GROUP BY d.date, d.hub_id
ORDER BY d.date;
```

```sql
-- Dock reboots (counter resets)
SELECT timestamp, dock_name, endpoint, press_total_count
FROM `schnell-home-automation.schnell_analytics.dock_logs`
WHERE counter_reset
ORDER BY timestamp DESC;
```

```sql
-- Health check: is the firmware reporting, or are we relying on polling?
SELECT source, COUNT(*) AS rows
FROM `schnell-home-automation.schnell_analytics.dock_logs`
GROUP BY source;
```

That last one is worth watching. Mostly `push` means the firmware reports
counter changes and telemetry is near-real-time. Mostly `poll` means push never
fires and rows arrive at the poll interval — accurate, just coarser. In that
case lower `dock_poll_interval` for finer granularity.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `No dock nodes found` | No commissioned node has a `Dock_` ProductName | Check the Matter Server dashboard → node → Node Info → ProductName. Add the actual prefix to `dock_product_names` |
| `matches a dock product name but exposes no vendor counter cluster` | Firmware lacks the counter cluster, or the node is not fully interviewed | Run **Interview** on the node in the Matter Server dashboard; verify the firmware exposes the vendor cluster |
| `Dock telemetry DISABLED — server rejected 'start_listening'` | The Matter Server is not the python-matter-server protocol this collector drives | Check the Matter Server add-on version. Event collection is unaffected |
| `Connection lost/refused` on repeat | Matter Server add-on not running, or a different URL | Confirm the Matter Server add-on is started; check `matter_server_url` |
| Counters recorded but `dock_name` empty | The dock is not in Custom Data Storage, or its `matter_node_id` is null *and* its docklet entities are not in HA's device registry | The log lists every dock/snap the store holds with its node id and entities. Re-save the dock in the app; see §3 "Linking the node when `matter_node_id` is missing" |
| `dock_name` populated but `docklet_label` empty | The docklet is unbound (`not_mapped`) | Expected — bind a device to that docklet in the app. `docklet_id` is still populated |
| `has no docklet at endpoint N` warning | The dock entry lists fewer docklets than the firmware has endpoints, or positions are recorded under an unrecognised key | The warning prints each docklet entry's key and fields; send that shape and the position key list can be extended |
| `matched it to Matter node N through Home Assistant's device registry` | `matter_node_id` is null — fallback 2 in §3 did its job | Working as intended. Fix `matter_node_id` in the app to remove the indirection |
| Rows only every 15 minutes | Firmware does not report the cluster, so only polling sees changes | Expected. Lower `dock_poll_interval` if finer granularity is needed |
| Deltas look far too large after an update | Add-on ran with an old state file, or presses happened while it was stopped | Expected — the delta covers the gap. The `*_count` columns remain accurate |
| A row shows `counter_reset` | The dock was power-cycled | Informational, not an error |
| `auto-detected dock counter cluster` in the log | Firmware's vendor cluster ID differs from the configured one | Update `dock_cluster_id` to the logged value. Collection continues either way |
| No rows in BigQuery, but the log says written | Extension installed after the rows were written, or wrong collection path | Verify the extension's collection path is `smash_db/{hubId}/dock_events` with collection-group query enabled |

Enable the `debug` option for per-attribute logging of every push event and poll
read.

---

## 11. Privacy

- Rows are keyed by raw MAC as `hub_id`, consistent with `ha_logs` and `app_logs`.
- Only counts and their timestamps are stored — no user identity, and no record
  of what any individual press did.
- Data travels hub → Firestore → BigQuery over the same service account and
  project as the existing event pipeline. No new external destination, and no
  Google Sheet or Drive access anywhere in the path.

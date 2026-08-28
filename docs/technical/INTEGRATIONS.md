# INTEGRATIONS.md

**Purpose:** how DigitalTwin.ai gets data out of a real plant, adapter by adapter, including the firewall rules and the failure behaviour.
**Status:** two adapters are built (`SimAdapter`, `CsvReplayAdapter`). The rest are designed and specified here but not implemented in the prototype. This is stated at the top of every section so no reader is misled.
**Last updated:** 2026-08-28

---

## 1. The adapter contract

Every source implements the same three-method protocol. Nothing writes.

```python
class SourceAdapter(Protocol):
    def describe(self) -> AdapterInfo:
        """Static description: protocol, endpoint, subscription count, declared
        polling rate, expected bandwidth. Shown in the data health panel so a
        controls engineer can see the load before approving."""

    async def stream(self) -> AsyncIterator[CanonicalEvent]:
        """Yield canonical events. Never blocks a source. Never retries in a
        tight loop. Raises on a connection failure so the supervisor can fail
        closed."""

    async def health(self) -> SourceHealth:
        """Last event time, events in the last minute, estimated clock skew,
        connection state."""
```

`AdapterInfo` is not decorative. It is what a plant reviewer reads to understand the
load a source will place on their system.

```python
@dataclass(frozen=True)
class AdapterInfo:
    adapter_id: str
    protocol: str                  # "opcua", "mtconnect", "sparkplug", "historian", "sim", "csv"
    endpoint: str
    mode: Literal["SUBSCRIBE", "POLL"]
    poll_interval_ms: int | None
    subscription_count: int
    expected_events_per_s: float
    expected_bandwidth_kbps: float
    adds_client_to_plc: bool       # true is a red flag and is surfaced as one
    firewall_rules: list[FirewallRule]
```

---

## 2. Source priority

A site is onboarded against whatever it already has, in this order of preference. The
order is by risk to the plant, not by convenience to us.

| Priority | Source | Why preferred |
|---|---|---|
| 1 | Existing historian (PI, Ignition, Wonderware, Aveva) | Already collecting. Query load lands on a system built for query load. Zero new touch on control equipment |
| 2 | Existing MQTT broker with Sparkplug B | Report-by-exception, already publishing, one subscriber added |
| 3 | Existing OPC UA server or aggregation server | Subscription-based, standard, already used by other consumers |
| 4 | Existing MTConnect agent | Common on machine tools, read-only by design |
| 5 | MES database read replica | Build records and inspection results, which the other sources rarely carry |
| 6 | New OPC UA client directly against a PLC | Last resort. Requires an explicit flag, a declared rate, and a documented approval |
| 7 | File drop (CSV, Parquet) on a schedule | Where a site will not open any port. Useful for retrospective replay evaluation |

Most sites will use two or three of these together: a historian or broker for cycle and
process data, plus an MES read replica for build records and inspection results.

---

## 3. Historian adapter (specified, not built)

**Sources:** OSIsoft PI, Ignition, Aveva, Wonderware Historian.

| Aspect | Detail |
|---|---|
| Mode | Poll, on a configured interval, typically 10 to 30 s |
| Query | Time-range query per tag group since the last high-water mark |
| Mapping | `SourceMapping` maps tag paths to canonical events |
| Load | One query per tag group per interval. Declared in `AdapterInfo` |
| Firewall | Outbound from DMZ to the historian's API port only |
| Clock | The historian's timestamps are used as `ts_source`. Historian clock quality is usually good and is measured anyway |
| Failure | Query error stops collection and raises a health event. No retry storm |
| Gotcha | Historians commonly apply compression and deadbands. A deadbanded cycle-time tag can hide exactly the small drift the product looks for. The adapter reads the tag's compression settings where the API exposes them and warns when a deadband exceeds the drift magnitudes we intend to detect |

That last row is the kind of detail that decides whether a deployment works, and it is
easy to discover only after two weeks of confusing results.

## 4. MQTT Sparkplug B adapter (specified, not built)

| Aspect | Detail |
|---|---|
| Mode | Subscribe |
| Topics | `spBv1.0/{group}/DDATA/{edge_node}/{device}` and the corresponding `NBIRTH` and `DBIRTH` for metric definitions |
| Mapping | Sparkplug metric aliases resolved from birth certificates, then mapped to canonical events |
| Load | One subscriber on an existing broker. Report-by-exception, so bandwidth tracks change rate rather than tag count (S-10) |
| Firewall | Outbound from DMZ to the broker port only |
| State | Sparkplug's birth and death certificates give source liveness directly, which feeds `SourceHealth` without a separate heartbeat |
| Failure | Broker disconnect raises a health event. Reconnect with capped backoff, never a tight loop |
| Gotcha | A rebirth after a broker restart re-sends the full state, which can look like a burst of simultaneous cycle completions. The adapter detects rebirth sequence numbers and suppresses the burst rather than passing it downstream as 400 events in one second |

## 5. OPC UA adapter (specified, not built)

| Aspect | Detail |
|---|---|
| Mode | Subscribe, with a configured publishing interval, typically 250 to 1000 ms |
| Nodes | Node IDs from `SourceMapping`. Monitored items grouped into a small number of subscriptions |
| Security | Sign and encrypt, certificate-based, using a client certificate the plant issues. Never `None` security mode, even on a trusted network |
| Load | Declared subscription count and publishing interval in `AdapterInfo`. A queue size of 1 with the latest-value discard policy, so a slow consumer cannot back up onto the server |
| Firewall | Outbound from DMZ to the OPC UA endpoint port (commonly 4840) only |
| Failure | Session loss raises a health event and stops collection. Reconnect with capped backoff |
| Gotcha | Connecting directly to a PLC's embedded OPC UA server adds scan-cycle load. This adapter sets `adds_client_to_plc = true` when the endpoint is a controller rather than an aggregation server, and the interface shows that flag prominently. Prefer an aggregation server |

## 6. MTConnect adapter (specified, not built)

| Aspect | Detail |
|---|---|
| Mode | Poll the agent's `/sample` endpoint with `from` and `count`, following the sequence number |
| Mapping | `dataItemId` to canonical events |
| Load | HTTP GET per interval against an agent designed for it |
| Firewall | Outbound from DMZ to the agent port (commonly 5000) only |
| Failure | A sequence gap (the agent's buffer rolled over) is detected from the returned `firstSequence` and recorded as a `data_gap`, not silently skipped |
| Gotcha | Agent buffers are finite. If the twin is down longer than the buffer covers, data is genuinely lost, and the twin records the gap rather than pretending the period was quiet |

## 7. MES adapter (specified, not built)

| Aspect | Detail |
|---|---|
| Mode | Poll a read replica or a reporting view, never the transactional database |
| Data | Build records keyed to a unit identifier, planned sequence, variant, part lot genealogy, inspection results, rework events |
| Mapping | Table and column to canonical event, in `SourceMapping` |
| Firewall | Outbound from DMZ to the replica's database port only, with a read-only account |
| Why it matters | This is the only source that reliably carries the unit key and the inspection outcome. Without a unit key, per-unit defect prediction is not possible, and the readiness assessment reports the site as not ready rather than degrading quietly (PRD assumption 2) |

## 8. File drop adapter (specified, partially built)

`CsvReplayAdapter` is built and reads a recorded canonical event file. The site-facing
variant, which reads a plant's own export format and maps it, is not.

This adapter is the most valuable one commercially and the least interesting technically.
It is how a retrospective evaluation is run against a plant's historian export with no
deployment, no port, and no risk, which USER_RESEARCH.md Section 4 identifies as the
single highest-value next study.

## 9. Built for the prototype

### `SimAdapter`
Reads the `plantsim` event stream. Applies the observability tier filter, so a Tier B
station emits only cycle events and a Tier C station emits nothing except downstream
scans and occasional manual checks. The simulator knows the ground truth; the adapter
does not pass it on.

### `CsvReplayAdapter`
Reads a recorded canonical event file with an optional speed multiplier. Used for
deterministic tests, for the evaluation harness, and for replaying a recorded scenario
during the demo without running the simulator live.

---

## 10. Clock handling

Different sources have different clocks and the differences matter, because a cycle time
computed across two sources with a 3 s skew is wrong by 3 s, which is comparable to the
drift magnitudes we intend to detect.

| Step | Detail |
|---|---|
| Estimate | For each pair of adapters observing the same unit handoff, maintain a rolling median of `ts_source` differences less nominal transport time |
| Report | Show the maximum estimated skew in the data health panel |
| Warn | Above `skew_warn_s` (default 2.0), raise a health event naming the two sources |
| Do not correct | The skew is not subtracted automatically. A correction applied to a genuinely slow station would hide the drift we are looking for. Instead, estimates spanning skewed sources carry a widened confidence and their `basis` says why |

---

## 11. Firewall rule summary

What a plant network team is actually asked to open. Every rule is outbound from the DMZ
host, and there are no inbound rules at all.

| Adapter | Direction | Destination | Port | Protocol |
|---|---|---|---|---|
| Historian | DMZ outbound | Historian API host | vendor-specific | HTTPS |
| Sparkplug | DMZ outbound | MQTT broker | 8883 | MQTT over TLS |
| OPC UA | DMZ outbound | Aggregation server | 4840 | OPC UA binary, sign and encrypt |
| MTConnect | DMZ outbound | Agent host | 5000 | HTTP |
| MES | DMZ outbound | Read replica | 1433 or 1521 or 5432 | Database over TLS |
| Web app | Plant LAN inbound to DMZ app host | App host | 443 | HTTPS |

The last row is the only inbound rule, and it is from the plant's office network to the
application, not from anywhere to the control network.

---

## 12. Onboarding a site

```
1. Readiness assessment
   Run the assessment against a sample export or a short live capture.
   Output: unit-key present, cycle event coverage, dark station share,
   historian availability, inspection results availability, clock quality.
   Result: READY | READY WITH INSTRUMENTATION | NOT READY, with specifics.

2. Topology discovery
   Feed a recorded stream to the discovery pass. It drafts a LineDefinition
   with a confidence per inferred field and marks what it could not infer.

3. Human correction
   An implementation engineer corrects the draft: buffer capacities, gate
   positions, rework loops, tier assignment. Typically half a day.

4. Source mapping
   Map the site's tags, topics or tables to canonical events. Typically one to
   three days depending on how many sources are involved.

5. Shadow period
   Every predictor starts in SHADOW for every station. Weeks 1 to 4 record and
   score without raising anything on the floor.

6. Promotion
   Stations begin clearing their gates from around week 4. The floor sees the
   first alert only from a predictor that has earned it on their line.
```

Steps 1 to 4 are the onboarding cost, and the honest answer is days to weeks depending on
source diversity, not the hours a vendor demo implies. Steps 5 and 6 are why a customer
sees nothing on the floor for a month, which is a commercial cost we accept for an
operational benefit (COMPETITIVE_ANALYSIS.md Section 7, item 6).

---

## 13. Standards this design follows

| Standard | Role here |
|---|---|
| ISA-95 (IEC 62264) | Level definitions and the enterprise-control boundary the deployment respects |
| Purdue reference model | Where the connector and application sit relative to the control network |
| IEC 62443 | Zone and conduit model, one conduit per source, no inbound path |
| ISO 23247 | Digital twin framework for manufacturing. Our observable-element to twin-element mapping follows its structure, which makes the design legible to anyone who has read the standard |
| OPC UA (IEC 62541) | Transport and security for the OPC UA adapter |
| MQTT Sparkplug B | Topic structure, birth and death certificates, report by exception |
| MTConnect | Agent query model and sequence handling |

References in RESEARCH_SOURCES.md, S-10, S-28 to S-30, S-49 to S-55.

---

## 14. Explicit non-integrations

| Not integrated | Reason |
|---|---|
| Any PLC write path | Architectural boundary |
| ERP | Nothing the twin decides needs ERP data |
| Warranty or field failure data | Interesting, and a different product |
| Supplier quality systems | Part lot is enough for containment; supplier scoring is not our job |
| Email, Teams, Slack alerting | Deferred. The primary channel is the line-side display, and adding a push channel before the trust ledger is proven would be exactly the wrong order |

That last row is a deliberate sequencing decision. Pushing unproven predictions into
someone's phone is the fastest known route to a system nobody trusts.

---

**Related:** [ARCHITECTURE.md](ARCHITECTURE.md) · [SECURITY_REQUIREMENTS.md](SECURITY_REQUIREMENTS.md) · [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) · [../../RESEARCH_SOURCES.md](../../RESEARCH_SOURCES.md)

# SECURITY_REQUIREMENTS.md

**Primary audience:** Arjun Nair, the controls and OT engineer whose sign-off this product needs. This is the first document handed to a plant IT or controls reviewer.
**Second audience:** the build agent, which must not violate any of these boundaries.
**Last updated:** 2026-08-28

---

## 1. The one commitment that matters

**DigitalTwin.ai never writes to a control system. There is no code path from this product to a PLC, SCADA node, MES record, or any Level 0 to 2 device.**

This is enforced structurally rather than by policy. The adapter protocol is:

```python
class SourceAdapter(Protocol):
    def describe(self) -> AdapterInfo: ...
    async def stream(self) -> AsyncIterator[CanonicalEvent]: ...
    async def health(self) -> SourceHealth: ...
```

Three methods, none of which writes. A reviewer can verify the claim by reading eight
lines. There is no configuration that enables writing, no admin mode, no escape hatch,
and adding one would require changing the protocol, which is a visible change in a pull
request rather than a flag someone flips at 2 am.

---

## 2. Network position

The deployment sits above the control network, in the DMZ, following the Purdue model
and IEC 62443 zone-and-conduit practice (S-49 to S-53).

```
 Level 0-2  field devices, PLCs, HMI, SCADA
     |
     |  existing plant infrastructure only
     v
 Level 3    historian, MES, OPC UA server, MQTT broker
     |
     |  ONE conduit, outbound from the plant's perspective, read-only
     v
 Level 3.5  DMZ:  site connector
     |
     v
 Level 3+   twin service, database, web app
```

| Requirement | Detail |
|---|---|
| SEC-01 | No inbound connection from the application zone to Level 2 or below |
| SEC-02 | The connector initiates all connections outward from the DMZ toward existing Level 3 infrastructure. Nothing in the plant initiates toward the twin |
| SEC-03 | One conduit, one protocol, one destination per source. No general-purpose tunnel |
| SEC-04 | Where the plant already operates a data diode or unidirectional gateway, the connector runs on the receive side and requires no exception |
| SEC-05 | Firewall rules required are enumerated per adapter in INTEGRATIONS.md, so a change request can be raised with a specific rule set rather than a request for access |

---

## 3. Load on plant systems

The second concern after write access, and the one that has actually caused incidents at
other sites.

| Requirement | Detail |
|---|---|
| SEC-10 | The connector prefers to consume infrastructure the plant already runs: an existing OPC UA server, an existing MTConnect agent, an existing MQTT broker, an existing historian. Adding a new client to a PLC requires an explicit configuration flag and is documented as a last resort |
| SEC-11 | Every adapter declares its polling rate, subscription count and expected bandwidth in `describe()`, and those values are shown in the data health panel. A reviewer can see the load before approving |
| SEC-12 | Subscription-based collection (OPC UA subscriptions, MQTT) is preferred over polling. Where polling is unavoidable, the rate is configured, capped, and never adaptive |
| SEC-13 | Backpressure: if the twin cannot keep up, it drops events and counts the loss visibly. It never slows a source, never retries aggressively, and never queues into the plant |
| SEC-14 | A single kill switch stops all collection: `docker compose stop connector`. Documented in the README and in the runbook |
| SEC-15 | The connector fails closed. A connection error stops collection and raises a health event. It does not retry in a tight loop |

---

## 4. Data handling

| Requirement | Detail |
|---|---|
| SEC-20 | All plant data stays within the plant's network boundary. The prototype runs entirely locally, and the production design is on-premises per plant. There is no cloud upload of event data |
| SEC-21 | Only aggregated scorecards and business-case inputs cross a site boundary for the Program view rollup. Never raw events, never unit-level records |
| SEC-22 | No third-party analytics, telemetry, error reporting, or font CDN in the web application. Fonts are self-hosted. Verified by a build check that fails on any external network reference |
| SEC-23 | The application runs fully offline after install (NFR-06) |
| SEC-24 | Database credentials come from the environment, never from a committed file. A pre-commit hook scans for secrets |
| SEC-25 | Data at rest encryption is the plant's storage decision. The product does not require plaintext access to anything it did not write |

---

## 5. Personal and operational data

Assembly line data contains information about identifiable people, which is easy to
overlook because it arrives as machine data.

| Requirement | Detail |
|---|---|
| SEC-30 | Operator identity is stored as an **operator group** identifier, not as a person. The model uses "shift A team 3", never a name or an employee number |
| SEC-31 | Where a site's source provides individual identifiers, the connector hashes them at ingest with a per-site salt. The raw identifier never reaches the database |
| SEC-32 | No view attributes a defect or a slow cycle to a named individual. The interface reports station and shift. This is a product decision, not only a privacy one: a tool used for individual performance management will be defeated by the people it monitors, and the data will get worse |
| SEC-33 | Operator-related features can be disabled entirely per site by configuration, with the model retrained without them, for sites whose works council or labour agreement requires it |
| SEC-34 | Retention of unit-level records is configurable per site to match the plant's own traceability retention policy, since automotive traceability requirements typically drive longer retention than we would choose |

SEC-32 deserves emphasis with the plant. The fastest way to destroy this product's data
quality is for the floor to learn it is being used to evaluate individuals.

---

## 6. Application security

Honest statement first: **the prototype has no authentication.** It ships with a persona
switcher and runs on localhost. The README says this plainly. What follows is the design
for a pilot, not a description of what exists.

| Requirement | Prototype | Pilot design |
|---|---|---|
| SEC-40 Authentication | None. Localhost only | OIDC against the plant's identity provider. No local password store |
| SEC-41 Authorisation | None | Three roles: `viewer` (all three views, read only), `supervisor` (adds counterfactuals, marking interventions, exports), `admin` (config reload, gate thresholds) |
| SEC-42 Line-side display | n/a | A kiosk role with no interactive capability, on a device-bound token, so an unattended wall display cannot be used to change anything |
| SEC-43 Audit | Config changes and gate-threshold changes recorded | Same, plus authenticated actor, retained with the ledger |
| SEC-44 Transport | HTTP on localhost | TLS, internal CA acceptable |
| SEC-45 Input validation | pydantic on every request body and every canonical event payload | Same |
| SEC-46 Injection | Parameterised queries throughout, no string-built SQL, ORM by default | Same |
| SEC-47 Dependencies | `pip-audit` and `npm audit` in CI, failing on high severity | Same, plus a pinned lockfile and a monthly review |
| SEC-48 Container | Non-root user, read-only root filesystem where practical, no capabilities added | Same, plus image scanning |
| SEC-49 CORS | Restricted to the app origin | Same |
| SEC-50 Rate limiting | None | Per-token limits on counterfactual and export endpoints, since both are expensive |

The gap between the two columns is stated rather than glossed, because a reviewer who
finds an unstated gap stops trusting the whole document.

---

## 7. Integrity of the evidence

The product's argument rests on its ledger. If the ledger can be edited, the argument is
worthless.

| Requirement | Detail |
|---|---|
| SEC-60 | `prediction` and `prediction_outcome` are append-only, enforced by a trigger and by a database role without UPDATE or DELETE grants on those tables |
| SEC-61 | Every prediction records an `inputs_hash` and a `model_version`, so it can be reproduced |
| SEC-62 | Outcome joining is automatic from the event stream. No human labels anything in the core loop, so no human can improve the numbers |
| SEC-63 | The simulator's ground truth is written to a separate schema with a separate role. The twin's database role has no grant on it. This prevents an accidental join that would silently invalidate every evaluation number |
| SEC-64 | Evaluation runs record their seed, configuration version and code version, so any published number can be reproduced exactly |
| SEC-65 | Gate thresholds are configuration, and changing them is an audited event that appears in the scorecard history. Loosening a gate to promote a failing predictor is visible |

---

## 8. Safety posture

| Requirement | Detail |
|---|---|
| SEC-70 | Every output is advisory. A human executes every action. There is no auto-apply, no scheduled action, no closed loop |
| SEC-71 | The product is not a safety system and does not claim to be. It does not replace, supplement, or interact with andon, e-stop, interlocks or any safety instrumented function |
| SEC-72 | A twin failure has no production consequence. The line runs identically with the twin stopped |
| SEC-73 | The interface never instructs a physical intervention with a safety implication. It reports a condition and a modelled effect. "Add a floater at S20" is a staffing suggestion; "bypass the interlock at S20" is not something this product can express |
| SEC-74 | Where a recommendation would require a maintenance window, that is stated, so nobody is nudged toward an unsafe in-production change |

---

## 9. What a plant reviewer should check

A short list a controls engineer can work through in twenty minutes.

1. Read `connector/protocol.py`. Confirm there is no write method.
2. Read `connector/*_adapter.py`. Confirm each implements only the protocol.
3. Run `grep -rn "write\|publish\|set_value\|WriteValue" connector/`. Confirm no hits
   against a source.
4. Read the firewall rules enumerated in INTEGRATIONS.md for the adapters you would
   enable. Confirm they are outbound-only from the DMZ.
5. Read the declared polling rates in each adapter's `describe()`.
6. Confirm the kill switch works: `docker compose stop connector`, then confirm the plant
   is unaffected and the interface shows its data age honestly.
7. Confirm operator identifiers are hashed at ingest by reading `connector/normalise.py`.
8. Confirm the database role used by the application has no grant on the truth schema.

This list is in the README as a section titled "For your controls engineer", because
making that review easy is the difference between a pilot in March and a pilot never.

---

## 10. Threats we considered and how we treat them

| Threat | Treatment |
|---|---|
| The connector is used as a pivot into OT | No inbound path exists. The conduit is outbound from the DMZ, one protocol, one destination |
| Collection load degrades a PLC scan cycle | Prefer existing infrastructure, declared and capped rates, subscription over polling, backpressure that drops rather than queues |
| A compromised twin gives false guidance | Every output is advisory, every prediction carries its evidence, and the scorecard makes a degrading predictor visible. A twin lying consistently would be caught by its own ledger |
| Ledger tampering to inflate accuracy | Append-only, role-restricted, automatic outcome joining, reproducible via inputs hash |
| Evaluation numbers contaminated by ground truth | Separate schema, separate role, no grant. Verified by a test |
| Unit-level data leaving the plant | On-premises deployment. Only aggregates cross a site boundary |
| The system used for individual performance management | Operator group only, hashed at ingest, disableable per site |
| Dependency supply chain | Pinned lockfiles, audit in CI, no runtime CDN, offline operation |

---

**Related:** [ARCHITECTURE.md](ARCHITECTURE.md) · [INTEGRATIONS.md](INTEGRATIONS.md) · [API_SPEC.md](API_SPEC.md) · [../product/USER_PERSONAS.md](../product/USER_PERSONAS.md)

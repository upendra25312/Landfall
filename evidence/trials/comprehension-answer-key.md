# Comprehension tasks + answer key (Trial A)

Give the participant the **tasks** only. Score against the **pass line**. Model
answers are for the facilitator.

---

## Task 1 — Explain the pipeline

**Prompt:** "In your own words, describe what happens between a client sending
their inventory files and Landfall producing an estimate. Name the stages and
say which parts a human still has to own."

**Pass line:** names the five stages in order (load &rarr; ingest/DQ &rarr; model
&rarr; assemble &rarr; publish, or clearly equivalent), states that the tools
compute and the agent orchestrates, and names at least two architect-owned
decisions (disposition fit, commercial terms, signing off, any Low-confidence
figure).

**Model answer:** Files upload to the engagement's private folder. Each is
detected, column-mapped, normalised and loaded into SQL, and a data-quality
report grades confidence and lists gaps. The agent then calls deterministic tools
— right-size every server to a VM SKU, price compute/storage/extras, design the
CAF landing zone, score 6&nbsp;R dispositions, plan waves. `assemble_estimate`
folds it into one package (8 sections, every figure an F-id, a calculation
appendix, an assumptions register); `publish_estimate` renders Excel/Word/PPT and
the POE. The architect owns whether each disposition suits the client's strategy,
the commercial terms, any Low-confidence number, and the final sign-off.

---

## Task 2 — Run an estimate and read a number

**Prompt:** "Using the engagement that already has data loaded, get the total
monthly Azure run-rate. Then tell me exactly how that number was calculated —
enough that you could defend it to the client."

**Pass line:** retrieves the run-rate total (from the dashboard or by asking in
chat); finds its `F-id`; opens the calculation appendix; states that the total is
compute + storage + run-rate extras, that compute is the per-server right-sized
SKU list priced at a stated region + retail date, and reads the confidence level
and the low/expected/high band off the figure.

**Model answer (sample estate):** run-rate ≈ **$113,911/month** ($1,366,927/yr) =
`compute_monthly` ($81,439, the right-sized SKU BoM at swedencentral retail) +
`storage_monthly` ($16,184, file/DB/object from the storage table) +
`extras_monthly` ($16,287, backup/monitoring/egress/support). Confidence on the
cost figure is **Low** — cost is capped at Low pre-discovery by design (a full
credit is a participant who says this, not one who says "Medium"). Each component
has its own appendix row with the formula and inputs; the pricing assumptions
(reserved-instance coverage, Azure Hybrid Benefit, price date) are numbered rows
in the register.

---

## Task 3 — Interpret a Low-confidence answer

**Prompt:** "Suppose the data-quality report puts the estimate at **Low**
confidence and the register says '62% of servers have no utilisation history'.
What does that mean for the number you'd give the client, and what do you do
next?"

**Pass line:** states that Low confidence is about the *input data*, not a
Landfall error; that right-sizing for those servers falls back to provisioned
specs + a margin so the number is a rough order of magnitude (likely
conservative); that you say so explicitly to the client; and that the fix is to
get the missing input (utilisation history / a discovery run) — named in the
register as a client-ask — not to ask Landfall to be more precise.

**Model answer:** The estate description is structurally thin. Landfall has still
produced a full number, but for the 62% without history it sized on the
provisioned CPU/RAM the client listed, which usually over-states real need — so
the figure is an upper-ish rough order of magnitude, not a defensible estimate.
Present it as a range with the caveat stated, and the very next step is the
data-gap the register names: collect utilisation data (Azure Migrate appliance,
vCenter export, or a monitoring pull) and re-run. Confidence rises automatically
when the data does.

---

## Scoring sheet

| | Task 1 pipeline | Task 2 run + trace | Task 3 Low confidence | Overall |
|---|---|---|---|---|
| Participant 1 | ☐ pass ☐ fail | ☐ pass ☐ fail | ☐ pass ☐ fail | |
| Participant 2 | ☐ pass ☐ fail | ☐ pass ☐ fail | ☐ pass ☐ fail | |
| Participant 3 | ☐ pass ☐ fail | ☐ pass ☐ fail | ☐ pass ☐ fail | |

Pass overall = all three tasks. Trial passes = all three participants pass overall.

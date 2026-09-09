# Trial protocol

Two independent trials. Run them with different people. Neither needs the code —
both are run against a **deployed** Landfall and the published docs.

---

## Trial A — Comprehension (Understandability dimension)

**5/5 bar (`audits/path-to-5x5.md` §6):** given only the docs, a consultant new to
Landfall can explain the pipeline, run an estimate, and correctly interpret a
Low-confidence answer — within an hour. Pass = **all 3 participants** succeed
unaided.

### Participants
3 people who have **not** worked on Landfall. Cloud-literate (they know what a VM
SKU and a landing zone are) but new to this tool. Not the author.

### Setup (facilitator, before)
1. A deployed Landfall URL + sign-in that works for the participant.
2. An engagement pre-loaded with the **sample estate** (so step 3's task has data).
3. Send only: the link to `docs/how-landfall-works.html` and `docs/operating-sop.html`.
4. Screen-share or a quiet room. Record start time.

### Procedure
- **0:00&ndash;0:20** — participant reads the two docs. No questions answered.
- **0:20&ndash;0:60** — participant works the 3 tasks in `comprehension-answer-key.md`,
  thinking aloud. The facilitator does **not** help; only unblocks tooling
  failures (a 500, a login loop) and notes them.
- Score each task pass/fail against the key. Note where the participant hesitated
  and which doc section they went back to.

### Acceptance
- All 3 participants pass all 3 tasks &rarr; **Understandability = 5.0**.
- 2 of 3, or partial passes &rarr; **3.5&ndash;4.0**, with the failing task's doc gap logged.
- Fewer &rarr; stays &le; 3.0; rewrite the weak section and re-run.

---

## Trial B — Usability (Usability dimension)

**5/5 bar (`audits/path-to-5x5.md` §5):** a pre-sales consultant who has never seen
the code produces a SoW-ready package from a fresh client dump in under a day,
with no engineer. Pass = all 3 produce an **architect-accepted** package, median
time **< 1 day**, and each can explain every section.

### Participants
3 pre-sales / solution consultants. Plus **1 migration architect** as the
independent acceptance reviewer (not the facilitator, not an author).

### Materials
3 distinct synthetic estates the participants have not seen — e.g. the three from
`evidence/backtest/estate_gen.py` exported to CSV, or three freshly generated
with `sample-estate/generate_estate.py` at new seeds. One estate per participant.

### Procedure
1. Give each participant: the deployed URL, `docs/operating-sop.html`,
   `docs/how-landfall-works.html`, and their estate's raw files (as a client would
   send them — CSV / Excel, no schema).
2. Task: "Produce a draft Azure migration estimate package (Excel + Word + deck)
   for this client, ready to hand to an architect." No engineer help; the
   facilitator only unblocks tooling failures and logs them.
3. Record wall-clock time to a published package (exclude waiting on a cold SQL
   or a calculator run — log those separately as environment latency).
4. The architect reviews each package **blind to the time taken** and rates it:
   *accept as-is* / *accept with light edits* / *needs rework*. "Light edits" =
   tracked-changes on wording + confirming assumptions, no re-derivation.
5. Debrief each participant: walk them through their own package section by
   section; note any section they cannot explain.

### Acceptance
- 3/3 *accept* or *accept with light edits*, median time < 1 day, all 3 explain
  every section &rarr; **Usability = 5.0**.
- 2/3, or median 1&ndash;2 days &rarr; **3.5&ndash;4.0**; log the blocker.
- Any *needs rework*, or an unexplainable section &rarr; stays &le; 3.0; fix and re-run.

### What to log regardless
- Every point a participant asked "what do I do now?" (a workflow-sequencing gap).
- Every field / toggle they got wrong (a UI-clarity gap — feeds Epic E12).
- Environment latency separately from participant time.

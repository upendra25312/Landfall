# Safe inventory schema updates

Cycle 55 replaces schema recreation with guarded table/index/function creation
and conditional additions of nullable columns. Existing rows, primary keys and
the RLS predicate are preserved. A missing required key/engagement column fails
with an explicit migration error; the script does not guess how to assign old rows
to customers. Existing type/key changes require a separately reviewed migration.

`scripts/apply_sql.py` validates the entire script before connecting, rejects
destructive statements (including dynamic SQL strings) and disabled RLS, applies
all schema batches in one transaction, and rolls back on any failure. Concurrent
runs serialize using a transaction-owned application lock. Identity grants remain
a separate step. This is a guard for trusted repository migrations, not a general
SQL sandbox for user input.

The schema enables the existing RLS policy and verifies coverage of all six tables.
It does not replace a pre-existing predicate definition. An unexpected predicate
definition requires investigation before migration approval.

Offline tests verify pre-execution rejection, rollback and schema/loader alignment.
Live replay passed twice: [C55 evidence](../evidence/cycles/c55/schema-replay.json)
records unchanged global table counts and full default-estate row hashes. The broader `azd provision` restriction
remains until infrastructure changes and all hooks have been reviewed. Fresh
deployment and teardown/restore validation remain deferred by the sponsor.

Reference: [SQL application locks](https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-getapplock-transact-sql).

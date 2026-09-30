# Runbook: DMSII Lock Contention Cascade

## Symptoms
- DMSII lock request failures or timeouts on a database structure (data set, set or the whole database).
- Several tasks waiting on the same structure; response times grow.
- One task chosen as a deadlock victim and discontinued (`DS ED`) with an ABEND record.
- Downstream tasks then fail or retry, producing a burst of related records.

## Likely causes
1. A long-running update transaction holding locks while other tasks queue.
2. Two tasks locking the same structures in different order (deadlock).
3. A batch job running during online hours.
4. Locks left behind by a task that hung or was discontinued.

## Diagnostic steps
1. Find the first lock timeout in the SUMLOG and identify the structure named.
2. List waiting tasks by mix number and find the task that held the lock earliest.
3. Identify the deadlock victim and read its `HISTORY` fault lines (see the task abend runbook).
4. Check whether a batch job started shortly before the first timeout.
5. Check for a hung task with no recent activity.

## Remediation
- Let the deadlock victim be discontinued; do not restart dependent tasks until the lock holder is resolved.
- If a task is hung, discontinue it (`DS`) after confirming with the application owner, so its locks are released.
- Re-run the victim transaction or batch step.
- Longer term: shorten transaction scope, lock structures in a consistent order and move batch work outside online hours.

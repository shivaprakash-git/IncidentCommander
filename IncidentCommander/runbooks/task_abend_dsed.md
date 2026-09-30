# Runbook: Task Abend (DS ED / Discontinued)

## Symptoms
- A task is discontinued: `P-DS`, `DS ED` or an ABEND record appears in the SUMLOG.
- A `HISTORY:` block follows with lines such as `Fault ...`, giving the fault reason and code location.
- The record carries the task name, code file and mix number.
- Dependent tasks may fail or wait after the abend.

## Likely causes
1. Program fault, for example invalid index, arithmetic overflow or invalid operand.
2. Resource failure: no disk space, file open failure or library linkage failure.
3. Deadlock victim selection in DMSII.
4. Operator or system discontinuation (`DS`) of a hung task.

## Diagnostic steps
1. Note the task name, code file, mix number and timestamp.
2. Read the `HISTORY` block from the bottom up: the last fault line is usually the trigger.
3. Search the SUMLOG for records with the same mix number just before the abend (opens, library links, security messages).
4. Check whether the same task abended earlier, and whether a software release changed recently.
5. Compare with disk, linkage and lock-contention incidents in the same time window.

## Remediation
- Resource cause: fix the resource (see the disk capacity, linkage failure or lock runbooks) and re-run.
- Program fault: collect the dump and history, then raise it with the application owner or software vendor.
- Hung task: confirm no locks remain and restart the job.
- Add the abend and its mix number to the incident timeline.

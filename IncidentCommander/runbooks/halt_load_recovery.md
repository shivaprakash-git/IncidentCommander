# Runbook: Halt/Load Recovery

## Symptoms
- An operator requests a halt/load, typically after a burst of security violations, a system hang, or unrecoverable resource problems.
- The SUMLOG shows a "GENERAL MCP INFORMATION" block with halt/load details at restart, and a gap in ordinary entries before it.
- Tasks that ran before the halt are absent, then restart in a new mix number range.

## Likely causes
1. Operator judgement after a hang or unresponsive console.
2. Security incident response (containment of a suspected attack).
3. Resource exhaustion (disk or memory) that could not be cleared online.
4. Software fault recorded in a memory dump.

## Diagnostic steps (before halt/load)
1. Confirm approval from the incident commander and application owners.
2. Preserve evidence: export the SUMLOG with LOGANALYZER, record the last mix numbers and the tasks active.
3. Capture dumps or console output relevant to the fault.
4. Confirm databases can recover (audit trail state) and that batch schedules are paused.

## Remediation
- Perform the halt/load per the site's operator procedure.
- After restart, review the "GENERAL MCP INFORMATION" block for halt reason and time.
- Verify libraries and services start; check for `LINKAGE FAILED` records that follow the restart.
- Verify database recovery completed and that disks are ready.
- Confirm that the original symptom is gone, then document the timeline, including the SUMLOG gap around the halt.
- Keep the pre-halt SUMLOG export with the incident record.

# Runbook: SUMLOG Full

## Symptoms
- The system log (SUMLOG) reports it is full or nearly out of space; new log entries may be at risk.
- Operators see a log-full message on the ODT/MARC console.
- In a LOGANALYZER export, entries may be missing across a time range. The banner `NO SUMLOG ENTRIES WERE DISCARDED` confirms nothing was lost; if it is absent, check the report for gaps.

## Likely causes
1. Heavy logging volume, for example a message storm from repeated failures.
2. The log family has too little disk space allocated.
3. Log entries not archived or squashed for a long period.

## Diagnostic steps
1. Identify the log volume trend and what generated the most entries (event class, task, station).
2. Check the log family for available disk space.
3. Confirm whether an archive or analysis run is pending on the current log.

## Remediation (operator procedure)
The following are operator commands entered through ODT/MARC. Confirm exact syntax against the site's MCP operations reference.
- `DL LOG`: display log information to see the current log state.
- `SQUASH`: compact the log and release space.
- `SUMLOGFULL=DISCARD`: the option that lets the system discard entries when the log is full. Entries are lost, so archive first where possible.
- `RC` (add a disk to the log family): use when more space is required.

Analyst actions, not operator commands: run LOGANALYZER to export entries before any discard, and check for the banner `NO SUMLOG ENTRIES WERE DISCARDED`.

After remediation, confirm new entries are being written and record any discard period as a data gap in the incident timeline.

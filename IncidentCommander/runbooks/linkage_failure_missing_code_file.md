# Runbook: Library Linkage Failure (Missing Code File / Library Not Initiated)

## Symptoms
- `LIB` records such as `*SYSTEM/NXEDIT/SUPPORT` or `*SYSTEM/JOBFORMATTER` followed by `LINK TO EXPORTING LIBRARY`.
- The record ends with `LINKAGE FAILED DUE TO MISSING CODE FILE` or `LINKAGE FAILED DUE TO LIBRARY NOT INITIATED`.
- Library attributes are listed, such as `INTNAME = SITESUPPORT, LIBACCESS = BYFUNCTION`.
- The calling task (for example JOBFILE/CONVERTER) may fail, run degraded, or be discontinued shortly afterwards.

## Likely causes
1. Missing code file: the code file the library name resolves to is absent, renamed, on an unavailable pack, or not what the SL (system library) function name maps to.
2. Library not initiated: the library exists but was not started, or its provider task ended, so the linking task cannot attach.
3. Wrong or stale SL function name, or a library directory changed after a software release install.
4. Recovery after a halt/load where a library expected to be running was not restarted.

## Diagnostic steps
1. Note the library name, the `INTNAME` and `LIBACCESS` attributes, and the calling task and mix number.
2. Check whether the same library failed earlier in the day or in the previous release period.
3. Confirm the code file exists on disk and matches the SL function mapping (use the system's file and library listing commands; names vary by site).
4. If the message says not initiated, check whether the library provider task is running.
5. Correlate with other records around the same second, such as security violations or DSS diagnostics that depend on the library.

## Remediation
- Missing code file: restore or copy the code file from the release media or backup, correct the SL function name if needed, and re-run the task.
- Library not initiated: start the library (or its provider job) and retry the calling task.
- Prevent recurrence: add the library to the start-up job list and verify library availability after software changes.
- Record the fix and the affected task mix numbers for the incident timeline.

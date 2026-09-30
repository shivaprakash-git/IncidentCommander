# Past incident PI-102: Library linkage failure after release install

**Date:** 2023-06-02 (fictional example)

## What happened
- 06:31:07 After a maintenance window, `LIB` record for `*SYSTEM/JOBFORMATTER` shows `LINKAGE FAILED DUE TO MISSING CODE FILE`.
- 06:31:08 Task JOBFILE/CONVERTER (mix 4412) starts and is discontinued with a `HISTORY: Fault` entry.
- 06:45:30 Same failure repeats for `*SYSTEM/NXEDIT/SUPPORT`, this time `LIBRARY NOT INITIATED`.
- 07:05:00 Operators report the morning batch run blocked.
- 07:20:00 The library directory entry is found pointing at the pre-upgrade code file name.

## Root cause
The release install renamed the code file, but the SL function mapping for the library still referenced the old name. The NXEDIT support library was also not restarted after the maintenance window.

## Resolution
The SL function name was corrected to the new code file, the support library was started, and JOBFILE/CONVERTER was re-run. The batch run finished 40 minutes late.

## Lesson
After any software release, verify library resolution and start-up before the batch window. Add `LINKAGE FAILED` to the post-maintenance SUMLOG check.

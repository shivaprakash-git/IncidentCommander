# Past incident PI-103: USERPK family full, file open failures

**Date:** 2023-09-21 (fictional example)

## What happened
- 13:50:12 `DISK` record `FAMILY USERPK SPACE LOW`.
- 14:05:44 Warning repeats; no action taken because it looked routine.
- 14:32:09 Task REPORTGEN (mix 5120) fails: `OPEN FAILED: NO DISK SPACE AVAILABLE`.
- 14:33:40 Three more tasks report area allocation errors; two are discontinued.
- 14:41:00 Operator reviews the file list and finds 60 GB of work files from job EXTRACT/DAILY.
- 15:02:00 Space cleared and failed tasks restarted.

## Root cause
Job EXTRACT/DAILY had a loop bug after a data change and wrote work files without limit, filling the USERPK family. The first `SPACE LOW` warning was not escalated.

## Resolution
The runaway job was stopped and its work files removed with the owner's approval. A spare disk was later added to the family. Failed tasks were re-run.

## Lesson
Treat repeated `SPACE LOW` records as the start of an incident. Alert at a lower threshold and keep a list of jobs that write large temporary files.

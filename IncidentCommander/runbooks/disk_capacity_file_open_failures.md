# Runbook: Disk Capacity and File Open Failures

## Symptoms
- `DISK` records such as `FAMILY USERPK SPACE LOW`.
- Task or file open errors such as `OPEN FAILED: NO DISK SPACE AVAILABLE`.
- Area allocation errors when a file grows or a new file is created.
- Application jobs slow down or are discontinued, and batch runs fail with file errors.

## Likely causes
1. The disk family (for example USERPK) is nearly full because of data growth, temporary files or old backups.
2. A runaway job creating large output or work files.
3. Fragmentation or oversized area requests that cannot be satisfied in one piece.
4. A disk in the family went offline, so capacity dropped suddenly.

## Diagnostic steps
1. From the SUMLOG, note when `SPACE LOW` first appeared and which family is affected.
2. List the tasks (mix numbers) whose opens failed and the files involved.
3. Check the family for free space and for units that are not ready.
4. Find the largest and most recently created files; look for temporary or duplicate files.
5. Check whether a job wrote unusually large output around the time the warning started.

## Remediation
- Free space: remove or archive files that are no longer needed, following site retention rules. Do not delete without owner approval.
- Add capacity: add a disk to the family (operator action) and confirm it is ready.
- Stop or fix the runaway job.
- Re-run the failed tasks after space is available.
- Monitor the family until usage stabilises and add a capacity alert at a lower threshold.

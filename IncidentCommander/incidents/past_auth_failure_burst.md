# Past incident PI-101: Authentication failure burst via NXEDIT

**Date:** 2023-03-14 (fictional example)

## What happened
- 09:02:11 First `SECURITY VIOLATION - INCORRECT USERCODE` (code 9) for usercode BKUMAR2 from station NXEDIT/IP10_32_198_140/1.
- 09:02:13 `DSS NXEDIT` reports `Linklibrary to GSSAPI failed`.
- 09:04:50 Violations repeat every 3 to 5 seconds; `MCS SECURITY VIOLATION: INVALID USERCODE/PASSWORD AT LOG ON` records accumulate.
- 09:10:20 Operator counts 180 violations, all from one IP and one usercode.
- 09:14:00 Usercode suspended; no further logon attempts reach MCS.
- 09:40:00 Platform team finds the GSSAPI library code file missing after a patch.

## Root cause
Kerberos logon could not initialise because the GSSAPI library was not found. A nightly client job fell back to usercode/password using an expired password and retried without limit. It was not an attack.

## Resolution
The GSSAPI code file was restored, the NXEDIT service restarted, the job owner reset the password and corrected the retry logic, and the usercode was re-enabled.

## Lesson
Check for `Linklibrary to GSSAPI failed` before assuming brute force. Add a retry cap to clients, and alert on repeated violations per usercode within five minutes.

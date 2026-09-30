# Runbook: Repeated Authentication Failures (Security Violation)

## Symptoms
- SUMLOG shows repeated `SECURITY VIOLATION - INCORRECT USERCODE` or `INCORRECT PASSWORD` records (violation codes 9 and 10), each paired with an `MCS SECURITY VIOLATION: INVALID USERCODE/PASSWORD AT LOG ON` record.
- The MCS record names the originating station, often an NXEDIT station such as `NXEDIT/IP10_32_198_136/1`, and the usercode (for example AMURAKI1).
- Nearby `DSS NXEDIT` diagnostics report `Linklibrary to GSSAPI failed` or `InitializeKerberosServer failed`.
- The same usercode and station repeat within seconds or minutes.

## Likely causes
1. Stale credentials: a user, script or scheduled client retries with an old password after a change or expiry.
2. Brute force or password guessing: many attempts, several usercodes, or an unfamiliar source IP.
3. Kerberos/GSSAPI misconfiguration: the GSSAPI library cannot be linked, so Kerberos logon fails and the client falls back to usercode/password, which then fails.
4. Mistyped usercode from a misconfigured connection profile.

## Diagnostic steps
1. Count violations per usercode, station and hour in the SUMLOG; note whether codes 9 (usercode) and 10 (password) alternate.
2. Extract the source IP from the station name and compare it with known client hosts.
3. Look for `Linklibrary to GSSAPI failed` or `InitializeKerberosServer failed` shortly before the first violation; if present, treat it as a configuration fault first.
4. Check whether the usercode is valid and when its password last changed.
5. Check for `LINKAGE FAILED` records on a GSSAPI-related library at the same time (see the linkage failure runbook).

## Remediation
- Stale credentials: have the owner update the client; reset the password if required.
- Suspected attack: suspend the usercode (per site security procedure), block the source IP at the network layer, and escalate to the security team. Keep the SUMLOG and security log for evidence.
- Kerberos/GSSAPI: verify the GSSAPI library is installed and its code file is present at the expected location, then restart the affected NXEDIT/DSS service. Confirm the Kerberos configuration with the platform team.
- Confirm resolution: no new violation records for the usercode over a full observation window.

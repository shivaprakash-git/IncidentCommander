"""Regexes shared by parser and discovery so both agree on what a header,
a day line and a noise line are."""
import re

# Header line: optional 0-6 leading spaces (LOGANALYZER uses 3, or 0 for the
# fractional-second TIME/DIAG style), HH:MM:SS[.ffff], then the rest.
# Continuation lines are indented >= 7 so they can never match.
HEADER_RE = re.compile(r"^ {0,6}(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?=\s|$)\s*(.*)$")

# Third shape: unindented, full date + fractional time (BNAV / TCPIP records).
DATED_HEADER_RE = re.compile(
    r"^(\d{2})/(\d{2})/(\d{4}) (\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?\s+(.*)$"
)

DAY_RE = re.compile(
    r"^\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})\s*$"
)

# Header body: [KEYWORD] <mix number> free text. The keyword is only accepted
# when a number follows it, so "NO SUMLOG ENTRIES WERE DISCARDED" stays INFO.
BODY_RE = re.compile(r"^(?:(?P<kw>[A-Z][A-Z0-9-]*|->)\s+)?(?P<num>\d+)(?:\s+(?P<text>.*))?$")

FILE_RECORDS_RE = re.compile(r"FILE CONTAINS (\d+) RECORDS")

# Lines that contain a discovery keyword but are boilerplate/config, not events.
NOISE_RE = re.compile(
    r"NO SUMLOG ENTRIES WERE DISCARDED"
    r"|RECOVERY\s*=\s*DISCARD"
    r"|SUMLOGFULL\s*[= ]\s*DISCARD"
    r"|HALT/LOAD\s+(?:UNIT|TIME)"
    r"|DURING HALT/LOADS"
    r"|HALT/LOADS?\s+(?:INFORMATION|COUNT)",
    re.IGNORECASE,
)

CRIT_RE = re.compile(
    r"SECURITY VIOLATION|\bHALT/LOAD\b|\bABEND|\bFATAL\b|\bFAULT(?:ED)?\b|\bDS'ED\b|\bDISCONTINUED\b|\bERROR\b",
    re.IGNORECASE,
)
WARN_RE = re.compile(
    r"\bINVALID\b|\bFAILED\b|\bVIOLATION\b|\bNOT FOUND\b|\bDENIED\b|\bMISSING\b|\bUNAUTHORIZED\b",
    re.IGNORECASE,
)

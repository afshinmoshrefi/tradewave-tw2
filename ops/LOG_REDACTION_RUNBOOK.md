# Credential-safe historical log redaction

`ops/redact_log_credentials.py` redacts three concrete credential shapes from
explicitly named plain or `.gz` logs: query assignments such as `token=` and
`api_key=`, JWT-shaped values in request/error text, and legacy
`/login/api/<key>` request paths. It reports counts only and never prints a match.

Always start with the default dry run, using explicit files rather than a directory:

```bash
python3 /home/flask/ops/redact_log_credentials.py \
  /var/log/tradewave/scorecard.log.1 \
  /var/log/tradewave/web.error.log.2.gz
```

For an active log, rotate it first and signal/restart its owning service so no process
keeps writing through the old file descriptor. Preserve a protected backup according
to the incident-retention policy, then apply only to the rotated files whose dry-run
counts were reviewed:

```bash
python3 /home/flask/ops/redact_log_credentials.py --apply \
  /var/log/tradewave/scorecard.log.1 \
  /var/log/tradewave/web.error.log.2.gz
```

Run the same command without `--apply` afterward; it must report zero replacements.
Redaction does not revoke a credential. Rotate/revoke exposed long-lived keys and JWT
signing material through the separate credential-rotation procedure when the incident
assessment requires it. Never paste matching log lines or raw values into a ticket.

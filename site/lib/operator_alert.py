"""Operator alert for jobs that must not fail silently.

Uses the existing Resend helper (``web/email_utils.resend_send_email``) and
``SUPPORT_EMAIL_TO``. Resend no-ops when ``RESEND_API_KEY`` or
``SUPPORT_EMAIL_FROM`` is empty or a placeholder. The caller still exits
non-zero; this module always prints the failure so the cron log is enough
when email is not configured.
"""

import sys
from pathlib import Path


def alert_operator(subject, body):
    """Print ``subject`` and try to email it. Return whether Resend accepted it.

    Never raises. A False return means the email was not sent; the printed
    ERROR and the caller's exit code are the alert.
    """
    banner = '=' * 70
    print(banner, file=sys.stderr)
    print('ERROR: %s' % subject, file=sys.stderr)
    print(body, file=sys.stderr)
    sent = False
    detail = (
        'operator email was NOT sent. Resend is unconfigured '
        '(RESEND_API_KEY or SUPPORT_EMAIL_FROM empty or placeholder) '
        'or the provider rejected the message. The non-zero exit code '
        'is the alert. Set those variables to also email SUPPORT_EMAIL_TO '
        '(default help@tradewave.ai).'
    )
    try:
        web_dir = Path(__file__).resolve().parents[2] / 'web'
        if str(web_dir) not in sys.path:
            sys.path.insert(0, str(web_dir))
        from email_utils import resend_send_email
        import config
        recipient = getattr(config, 'SUPPORT_EMAIL_TO', '') or ''
        if not recipient:
            detail = (
                'operator email was NOT sent. SUPPORT_EMAIL_TO is empty. '
                'The non-zero exit code is the alert.'
            )
        else:
            sent = bool(resend_send_email(
                to=recipient,
                subject=subject,
                body_text=body,
            ))
            if sent:
                detail = 'operator email sent via Resend to SUPPORT_EMAIL_TO'
    except Exception as exc:
        detail = 'operator email failed (%s). The non-zero exit code is the alert.' % (
            type(exc).__name__,
        )
    print(detail, file=sys.stderr)
    print(banner, file=sys.stderr)
    return sent

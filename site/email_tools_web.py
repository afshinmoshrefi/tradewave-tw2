"""
Minimal Mailerlite campaign helpers for the WEB tier (daily AI pick email).

Extracted from smn/email_tools.py — ONLY the create/schedule-campaign path,
with none of the SMN/redis/pandas imports, so it runs on the web box where the
SMN stack isn't installed. Tracked in git so deploys carry it.
"""
import sys
sys.path.insert(0, '/home/flask')
import mailerlite as MailerLite
import config

mailerlite_token = (getattr(config, 'mailerlite_token', None)
                    or getattr(config, 'MAILERLITE_API_KEY', None)
                    or getattr(config, 'MAILERLITE_TOKEN', None))


def create_campaign(campaign_name, subject, from_name, from_email, group_id, content):
    """Create a regular Mailerlite campaign. Returns (campaign_id, created_at)."""
    client = MailerLite.Client({'api_key': mailerlite_token})
    params = {
        "name": campaign_name,
        "language_id": 4,
        "type": "regular",
        "emails": [{
            "subject": subject,
            "from_name": from_name,
            "from": from_email,
            "content": content,
        }],
        "groups": [group_id],
    }
    response = client.campaigns.create(params)
    return int(response['data']['id']), response['data']['created_at']


def schedule_campaign(campaign_id, send_date, send_hour, send_minute):
    """Schedule a created campaign for delivery."""
    client = MailerLite.Client({'api_key': mailerlite_token})
    params = {
        "delivery": "scheduled",
        "schedule": {"date": send_date, "hours": send_hour, "minutes": send_minute},
    }
    return client.campaigns.schedule(campaign_id, params)

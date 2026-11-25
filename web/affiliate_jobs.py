"""Background jobs of the partner program (TW-TASK-0039, fix-0039).

Why: two kinds of work are too slow for a web request and used to hold a
gunicorn worker: sending one message to a GROUP of partners (one Resend call
per partner) and asking the model to propose a general knowledge-base entry.

How (chosen for robustness over a background thread): the request writes ONE
row to affiliate_jobs and returns. This module, run by cron every 2 minutes
(ops/install_affiliate_comms_cron.sh) and again by the daily comms job, claims
queued rows and runs them. The row is the durable status record: queued ->
running -> done | failed, with attempts, result and the last error. A web
restart, a crash mid-send or a deploy loses nothing: a row left 'running' for
more than STALE_AFTER is queued again, and every handler is idempotent (a
message is delivered once per partner by its event key; a proposal just
overwrites the proposal fields).

  python web/affiliate_jobs.py            run everything that is queued
  python web/affiliate_jobs.py --list     show the newest jobs

Job kinds are STORAGE IDs (affiliate_jobs.kind): never rename, only add.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WEB_ROOT = Path(__file__).resolve().parent
for _candidate in (str(_REPO_ROOT), str(_WEB_ROOT)):
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

log = logging.getLogger("tw2.affiliate_jobs")

UTC = dt.timezone.utc
MAX_ATTEMPTS = 5
STALE_AFTER = dt.timedelta(minutes=15)
KIND_LABEL = {"send_message": "Group message", "propose_general": "Suggest a general answer"}


def _now(now=None):
    if now is None:
        return dt.datetime.now(UTC)
    return now if now.tzinfo else now.replace(tzinfo=UTC)


def _aware(v):
    return v if v is None or v.tzinfo else v.replace(tzinfo=UTC)


def enqueue(session, kind, payload, created_by=None, now=None):
    """Queue one job. Commits. Returns the row."""
    from models import AffiliateJob
    if kind not in HANDLERS:
        raise ValueError("unknown job kind %r" % kind)
    job = AffiliateJob(kind=kind, payload=dict(payload or {}), status="queued", attempts=0,
                       created_by=created_by, created_at=_now(now))
    session.add(job)
    session.commit()
    return job


# ---------------------------------------------------------------------------
# handlers: fn(session, payload) -> JSON-able result. Raise to retry.
# ---------------------------------------------------------------------------
def _run_send_message(session, payload):
    import affiliate_comms as comms
    from models import AffiliateMessage
    msg = session.get(AffiliateMessage, int(payload["message_id"]))
    if msg is None:
        return {"skipped": "message no longer exists"}
    stats = comms.deliver_message(session, msg, payload.get("recipient_ids") or [])
    if stats["failed"]:
        # deliver() keeps its own per-partner retry count; run again later so
        # the failed sends get their retries. Already-sent partners are skipped.
        raise RuntimeError("%d of %d sends failed" % (stats["failed"], stats["recipients"]))
    return stats


def _run_propose_general(session, payload):
    import affiliate_help as ah
    from affiliate_help_models import AffiliateHelpKb
    kb = session.get(AffiliateHelpKb, int(payload["kb_id"]))
    if kb is None or kb.scope != "partner" or kb.status != "active":
        return {"skipped": "entry is gone, retired or already general"}
    return {"proposed": bool(ah.propose_general(session, kb))}


HANDLERS = {"send_message": _run_send_message, "propose_general": _run_propose_general}


def _claim(session, job, now):
    """queued -> running, atomically (two runners never take the same job)."""
    from models import AffiliateJob
    n = (session.query(AffiliateJob)
         .filter(AffiliateJob.id == job.id, AffiliateJob.status == "queued")
         .update({"status": "running", "started_at": now,
                  "attempts": AffiliateJob.attempts + 1}, synchronize_session=False))
    session.commit()
    if n:
        session.refresh(job)
    return bool(n)


def run_pending(session, limit=50, now=None) -> dict:
    """Run queued jobs, oldest first. Never raises for a failing job."""
    from models import AffiliateJob
    now = _now(now)
    stats = {"done": 0, "retry": 0, "failed": 0}
    for stale in (session.query(AffiliateJob).filter(AffiliateJob.status == "running").all()):
        started = _aware(stale.started_at)
        if started is None or now - started > STALE_AFTER:
            stale.status = "queued" if int(stale.attempts or 0) < MAX_ATTEMPTS else "failed"
            stale.error = "runner stopped before the job finished"
    session.commit()
    jobs = (session.query(AffiliateJob).filter(AffiliateJob.status == "queued")
            .order_by(AffiliateJob.id).limit(limit).all())
    for job in jobs:
        if not _claim(session, job, now):
            continue
        job_id, kind, attempts = job.id, job.kind, int(job.attempts or 0)
        try:
            result = HANDLERS[kind](session, dict(job.payload or {}))
            job = session.get(AffiliateJob, job_id)
            job.status, job.result, job.error, job.finished_at = "done", result, None, _now()
            session.commit()
            stats["done"] += 1
        except Exception as e:   # noqa: BLE001  (one job must not stop the others)
            session.rollback()
            job = session.get(AffiliateJob, job_id)
            final = attempts >= MAX_ATTEMPTS
            job.status = "failed" if final else "queued"
            job.error = ("%s: %s" % (type(e).__name__, e))[:500]
            job.finished_at = _now() if final else None
            session.commit()
            stats["failed" if final else "retry"] += 1
            log.warning("job %s (%s) attempt %d failed: %s", job_id, kind, attempts,
                        type(e).__name__)
    return stats


def counts(session) -> dict:
    from models import AffiliateJob
    from sqlalchemy import func
    out = {"queued": 0, "running": 0, "failed": 0}
    for status, n in (session.query(AffiliateJob.status, func.count())
                      .filter(AffiliateJob.status.in_(tuple(out)))
                      .group_by(AffiliateJob.status).all()):
        out[status] = int(n)
    return out


def job_for_message(session, message_id):
    """The newest send job of one admin message, or None (sent inline)."""
    from models import AffiliateJob
    for job in (session.query(AffiliateJob).filter(AffiliateJob.kind == "send_message")
                .order_by(AffiliateJob.id.desc()).limit(200).all()):
        if str((job.payload or {}).get("message_id")) == str(message_id):
            return job
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run queued partner-program background jobs.")
    ap.add_argument("--list", action="store_true", help="show the newest jobs and exit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s affiliate_jobs: %(message)s")
    import models
    s = models.Session()
    try:
        if args.list:
            for j in (s.query(models.AffiliateJob).order_by(models.AffiliateJob.id.desc())
                      .limit(30).all()):
                print("%6d  %-16s %-8s attempts=%d  %s" % (j.id, j.kind, j.status,
                                                          int(j.attempts or 0), j.error or ""))
            return 0
        stats = run_pending(s)
    finally:
        s.close()
    if any(stats.values()):
        log.info("done: %s", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())

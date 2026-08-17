"""Deterministic statistics over tracked applications.

Counts and rates are computed here in plain Python rather than asked of the
LLM — models are unreliable at exact arithmetic, and CLAUDE.md's guiding
principle is that AI analysis must be explainable and evidence-based. The
LLM (see prompts.py/ollama_client.py) only ever receives these numbers, it
never recomputes them.
"""

STATUSES = ["Pending", "Applied", "Interview", "Offer", "Rejected", "Withdrawn", "Ghosted", "Ignored"]

# Applications still in flight have no outcome yet, so they're excluded from
# rate denominators — including them would understate rates for anyone who
# just started applying.
NO_OUTCOME_STATUSES = {"Pending"}


def compute_stats(applications):
    by_status = {status: 0 for status in STATUSES}
    for app in applications:
        status = app.get("status")
        if status in by_status:
            by_status[status] += 1
        else:
            by_status.setdefault("Unknown", 0)
            by_status["Unknown"] += 1

    total = len(applications)
    decided = sum(count for status, count in by_status.items() if status not in NO_OUTCOME_STATUSES)

    interview_count = by_status.get("Interview", 0) + by_status.get("Offer", 0)
    offer_count = by_status.get("Offer", 0)

    return {
        "total": total,
        "byStatus": by_status,
        "interviewRate": round(interview_count / decided, 3) if decided else None,
        "offerRate": round(offer_count / decided, 3) if decided else None,
    }

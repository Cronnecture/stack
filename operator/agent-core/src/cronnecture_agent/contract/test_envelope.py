"""Contract envelope helpers."""

from cronnecture_agent.contract.envelope import includes, paginate, parse_query, job_status
from cronnecture_agent.contract.reads import ContractReads


def test_paginate_cursor():
    items = [{"id": i} for i in range(5)]
    q = parse_query({"limit": "2", "cursor": "2"})
    page = paginate(items, q)
    assert page["total"] == 5
    assert [x["id"] for x in page["items"]] == [2, 3]
    assert page["nextCursor"] == "4"


def test_job_status():
    assert job_status("pending") == "queued"
    assert job_status("completed") == "ok"
    assert job_status("failed") == "failed"
    assert job_status("dismissed") == "ok"


def test_includes():
    assert includes("cp-master-01 fra", "master")
    assert not includes("worker", "master")


def test_dismissed_jobs_are_not_attention():
    jobs = [
        {
            "id": "20960",
            "type": "fleet_converge",
            "target": "fleet",
            "status": "ok",
            "startedAt": "2026-08-24T21:00:00",
            "detail": "Dismissed (was failed): Auto-cleared: later success of same operation",
        },
        {
            "id": "20941",
            "type": "fleet_converge",
            "target": "fleet",
            "status": "failed",
            "startedAt": "2026-08-24T20:00:00",
            "detail": "playbook failed",
        },
        {
            "id": "1",
            "type": "backup",
            "target": "cp-master-01",
            "status": "failed",
            "startedAt": "2026-08-24T19:00:00",
            "detail": "disk full",
        },
    ]
    open_failed = ContractReads._actionable_failed_jobs(jobs)
    assert [j["id"] for j in open_failed] == ["1"]
    items = ContractReads.attention(None, [], jobs, [])
    assert [i["id"] for i in items] == ["job-1"]

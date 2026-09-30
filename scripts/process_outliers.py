#!/usr/bin/env python3
"""
ATS-score every job against the resume skill graph, then emit recommendation outliers.

Usage
  process_outliers.py [--offline] [--min-score 55] [--max-missing 2]
                      [--pct-low 5] [--pct-high 10]

Scores from Neo4j (run parse_and_ingest.py first) unless --offline or Neo4j is unreachable.
Writes web/analysis.json consumed by the static recommendation dashboard.

Outlier definition
  ATS score >= min_score, 1..max_missing missing skills, none critical.
  Optionally further restricted to the top [pct-low, pct-high] percent of scores
  so the dashboard shows only the highest-ranked recommendation band.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from common import (
    ROOT,
    have_weights,
    job_terms,
    load_jobs,
    parse_resume,
    score_job,
    select_top_percentile_outliers,
)

CYPHER = """
MATCH (j:Job)-[r:REQUIRES]->(s:Skill)
OPTIONAL MATCH (c:Candidate {id:$cid})-[h:HAS_SKILL]->(s)
RETURN j.id AS id, j.title AS title, j.company AS company, j.location AS location,
       collect({skill:s.name, critical:r.critical, w:h.weight}) AS reqs
"""


def from_neo4j(cid: str):
    from neo4j import GraphDatabase

    auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "changeme123"))
    with GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://localhost:7687"), auth=auth) as d:
        d.verify_connectivity()
        rows = d.execute_query(CYPHER, cid=cid, database_=os.getenv("NEO4J_DATABASE", "neo4j"))[0]
    jobs, have = [], {}
    for r in rows:
        jobs.append({
            "id": r["id"],
            "title": r["title"],
            "company": r["company"],
            "location": r["location"],
            "required": [{"skill": q["skill"], "critical": q["critical"]} for q in r["reqs"]],
        })
        have.update({q["skill"]: q["w"] for q in r["reqs"] if q["w"] is not None})
    return jobs, have


def main() -> None:
    ap = argparse.ArgumentParser(description="Score jobs and emit ATS recommendation outliers")
    ap.add_argument("--offline", action="store_true", help="Skip Neo4j; score from local files only")
    ap.add_argument("--min-score", type=float, default=55.0, help="Minimum ATS score for outlier (50-60 typical)")
    ap.add_argument("--max-missing", type=int, default=2, help="Max non-critical missing skills")
    ap.add_argument("--pct-low", type=float, default=5.0, help="Lower bound of top-score percentile band")
    ap.add_argument("--pct-high", type=float, default=10.0, help="Upper bound of top-score percentile band")
    a = ap.parse_args()

    file_jobs = load_jobs()
    cand = parse_resume(extra_terms=job_terms(file_jobs))
    jobs, have, source = file_jobs, have_weights(cand["skills"]), "offline"
    if not a.offline:
        try:
            jobs, have = from_neo4j(cand["id"])
            source = "neo4j"
        except Exception as exc:
            print(f"Neo4j unavailable ({exc}); falling back to offline mode")

    scored = sorted(
        (score_job(j, have, a.min_score, a.max_missing) for j in jobs),
        key=lambda r: (-r["ats_score"], len(r["missing"])),
    )
    # Strict recommendation set: outliers that also sit in the top 5–10% score band
    recommendations = select_top_percentile_outliers(scored, a.pct_low, a.pct_high)
    # If the percentile band is empty (small job set), fall back to all outliers sorted by score
    if not recommendations:
        recommendations = [j for j in scored if j["outlier"]]

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "candidate": cand["name"],
        "thresholds": {
            "min_score": a.min_score,
            "max_missing": a.max_missing,
            "pct_low": a.pct_low,
            "pct_high": a.pct_high,
        },
        "skills": sorted(
            ({"name": k, **v} for k, v in cand["skills"].items()),
            key=lambda x: (x["category"], x["name"]),
        ),
        "credentials": cand["credentials"],
        "experiences": cand["experiences"],
        "jobs": scored,
        "recommendations": recommendations,
    }
    path = ROOT / "web" / "analysis.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(
        f"[{source}] {len(out['skills'])} skills | {len(scored)} jobs scored | "
        f"{sum(j['outlier'] for j in scored)} outliers | "
        f"{len(recommendations)} recommendations (top {a.pct_low}-{a.pct_high}%) -> {path}"
    )


if __name__ == "__main__":
    main()

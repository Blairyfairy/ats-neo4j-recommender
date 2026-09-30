#!/usr/bin/env python3
"""
Parse index.html into a skill graph and load it into Neo4j AuraDB (or local Neo4j).

Graph model
  (Candidate)-[:HAS_SKILL {source,weight,evidence}]->(Skill)-[:IN_CATEGORY]->(Category)
  (Candidate)-[:HOLDS]->(Credential)-[:VALIDATES]->(Skill)
  (Candidate)-[:HAD_EXPERIENCE]->(Experience)-[:USED]->(Skill)
  (Job)-[:REQUIRES {critical}]->(Skill)
"""
from __future__ import annotations

import os
import sys
import time

from neo4j import GraphDatabase

from common import WEIGHTS, job_terms, load_jobs, norm, parse_resume

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "changeme123"))
DB = os.getenv("NEO4J_DATABASE", "neo4j")


def connect(retries: int = 30, delay: int = 5):
    for i in range(retries):
        try:
            driver = GraphDatabase.driver(URI, auth=AUTH)
            driver.verify_connectivity()
            return driver
        except Exception as exc:
            print(f"Neo4j not ready ({exc}); retry {i + 1}/{retries}")
            time.sleep(delay)
    sys.exit("Could not connect to Neo4j")


def ingest(driver) -> None:
    jobs = load_jobs()
    cand = parse_resume(extra_terms=job_terms(jobs))
    cid = cand["id"]
    rows = [
        {
            "name": n,
            "category": v["category"],
            "source": v["source"],
            "weight": WEIGHTS[v["source"]],
            "evidence": v["evidence"],
        }
        for n, v in cand["skills"].items()
    ]
    with driver.session(database=DB) as s:
        for q in (
            "CREATE CONSTRAINT skill_name IF NOT EXISTS FOR (x:Skill) REQUIRE x.name IS UNIQUE",
            "CREATE CONSTRAINT cand_id IF NOT EXISTS FOR (c:Candidate) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT job_id IF NOT EXISTS FOR (j:Job) REQUIRE j.id IS UNIQUE",
            "CREATE CONSTRAINT cred_name IF NOT EXISTS FOR (d:Credential) REQUIRE d.name IS UNIQUE",
            "CREATE CONSTRAINT exp_id IF NOT EXISTS FOR (e:Experience) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT cat_name IF NOT EXISTS FOR (g:Category) REQUIRE g.name IS UNIQUE",
        ):
            s.run(q)
        s.run("MERGE (c:Candidate {id:$id}) SET c.name=$name", id=cid, name=cand["name"])
        s.run("MATCH (c:Candidate {id:$id})-[r:HAS_SKILL|HOLDS|HAD_EXPERIENCE]->() DELETE r", id=cid)
        s.run(
            """MATCH (c:Candidate {id:$id}) UNWIND $rows AS r
               MERGE (k:Skill {name:r.name}) SET k.category=r.category
               MERGE (g:Category {name:r.category}) MERGE (k)-[:IN_CATEGORY]->(g)
               MERGE (c)-[h:HAS_SKILL]->(k) SET h.source=r.source, h.weight=r.weight, h.evidence=r.evidence""",
            id=cid, rows=rows,
        )
        s.run(
            """MATCH (c:Candidate {id:$id}) UNWIND $rows AS r
               MERGE (d:Credential {name:r.name}) SET d.issued=r.issued, d.expires=r.expires,
                     d.credential_id=r.credential_id, d.year=r.year
               MERGE (c)-[:HOLDS]->(d)
               WITH d, r UNWIND r.skills AS sk MATCH (k:Skill {name:sk}) MERGE (d)-[:VALIDATES]->(k)""",
            id=cid, rows=cand["credentials"],
        )
        s.run(
            """MATCH (c:Candidate {id:$id}) UNWIND $rows AS r
               MERGE (e:Experience {id:r.id}) SET e.company=r.company, e.dates=r.dates, e.roles=r.roles
               MERGE (c)-[:HAD_EXPERIENCE]->(e)
               WITH e, r UNWIND r.skills AS sk MATCH (k:Skill {name:sk}) MERGE (e)-[:USED]->(k)""",
            id=cid, rows=cand["experiences"],
        )
        for j in jobs:
            s.run(
                "MERGE (j:Job {id:$id}) SET j.title=$t, j.company=$co, j.location=$loc",
                id=j["id"], t=j["title"], co=j["company"], loc=j.get("location", ""),
            )
            s.run("MATCH (:Job {id:$id})-[old:REQUIRES]->() DELETE old", id=j["id"])
            s.run(
                """MATCH (j:Job {id:$id}) UNWIND $reqs AS r MERGE (k:Skill {name:r.n})
                   MERGE (j)-[q:REQUIRES]->(k) SET q.critical=r.crit""",
                id=j["id"],
                reqs=[{"n": norm(r["skill"]), "crit": bool(r.get("critical"))} for r in j["required"]],
            )
    print(
        f"Ingested {len(rows)} skills, {len(cand['credentials'])} credentials, "
        f"{len(cand['experiences'])} experiences, {len(jobs)} jobs"
    )


if __name__ == "__main__":
    drv = connect()
    ingest(drv)
    drv.close()

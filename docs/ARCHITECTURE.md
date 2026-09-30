# Ideal AWS Architecture — ATS Neo4j Recommendation System

Production-grade, multi-AZ, highly available design for the skill-graph ATS Neo4j recommender.

---

## Why this stack (not pure Amazon Personalize)

| Concern | Amazon Personalize | This architecture |
|---------|--------------------|-------------------|
| Core signal | User–item interaction history | Explicit skill graph + critical flags |
| Cold start | Needs interaction volume | Works from day-1 resume parse |
| Explainability | Black-box scores | Matched / missing skills per job |
| Outlier definition | Rank by predicted click | Deterministic: top 5–10% ATS + non-critical gaps only |
| Graph relationships | Flat feature store | Native Neo4j paths (skill → category → experience) |

**Amazon Personalize** (or SageMaker embeddings + vector search) is an optional **re-ranker** once you collect click/apply events. The primary engine stays the ATS skill-graph pipeline because job matching is a reciprocal, constraint-heavy problem (critical skills, missing-skill count), not pure collaborative filtering.

---

## Target architecture (single region, 3 AZs)

```
                         ┌──────────────────────────────┐
                         │     Amazon Route 53 (DNS)     │
                         │   health-checked alias A/AAAA │
                         └──────────────┬───────────────┘
                                        │
                         ┌──────────────▼───────────────┐
                         │  CloudFront (optional HTTPS)  │
                         │  + ACM certificate            │
                         └──────────────┬───────────────┘
                                        │
              ┌─────────────────────────▼─────────────────────────┐
              │           Application Load Balancer               │
              │     multi-AZ · public subnets · HTTPS (443)       │
              └─────────┬───────────────────────┬─────────────────┘
                        │                       │
         ┌──────────────▼──────┐   ┌────────────▼──────────────┐
         │  ECS Fargate tasks  │   │  ECS Fargate tasks         │
         │  (recommendation    │   │  (recommendation API /     │
         │   static + API)     │   │   static)                  │
         │  private subnets    │   │  private subnets           │
         │  AZ-a / AZ-b / AZ-c │   │  AZ-a / AZ-b / AZ-c        │
         └──────────┬──────────┘   └────────────┬───────────────┘
                    │                           │
                    └─────────────┬─────────────┘
                                  │
              ┌───────────────────▼───────────────────┐
              │     VPC Interface Endpoints           │
              │  Secrets Manager · S3 · ECR · Logs    │
              └───────────────────┬───────────────────┘
                                  │
              ┌───────────────────▼───────────────────┐
              │  AWS PrivateLink → Neo4j AuraDB       │
              │  (Enterprise / Virtual Dedicated      │
              │   Cloud tier, multi-AZ Aura cluster)  │
              │  ports 7687 (Bolt) + 7473 (HTTPS)     │
              └───────────────────────────────────────┘

Batch pipeline (EventBridge schedule)
  EventBridge rule (e.g. daily 02:00 UTC)
       → Step Functions state machine
            → ECS RunTask (parse + ingest)
            → ECS RunTask (score + write analysis.json to S3)
            → invalidate CloudFront (optional)
```

---

## Networking (ideal)

| Layer | Choice | Why |
|-------|--------|-----|
| VPC | Custom, `/16`, **3 AZs** | AZ independence (Well-Architected REL10) |
| Public subnets | 1 per AZ, `/24` | ALB only |
| Private app subnets | 1 per AZ, `/24` | Fargate tasks — no public IPs |
| Private data endpoints | Interface VPC endpoints | Secrets Manager, ECR, CloudWatch Logs, S3 gateway |
| Neo4j | **PrivateLink** (Aura Enterprise) | No public internet path for graph traffic |
| Security groups | Least privilege | ALB→task :8080; task→PrivateLink :7687/7473; endpoints only from task SG |
| NACLs | Default allow (or tighten egress) | Optional defense-in-depth |

AuraDB Free/Professional talk to the public Bolt endpoint over TLS. For the ideal private path, use **Aura Enterprise / Virtual Dedicated Cloud** and accept the PrivateLink connection in the Aura console.

---

## Compute & serving (HA)

| Component | Setting |
|-----------|---------|
| ECS cluster | Fargate, capacity providers FARGATE + FARGATE_SPOT (optional) |
| Service | Desired count ≥ **2**, spread across 3 AZs (`awsvpc` + multiple private subnets) |
| Task | 0.5–1 vCPU / 1–2 GB; health check `/` or `/health` |
| ALB | Cross-zone load balancing **enabled**; target group health checks; deregistration delay 30s |
| Auto scaling | Target tracking on ALB `RequestCountPerTarget` or CPU 50% |
| Deployment | Rolling, min healthy 100%, max 200% |

Static dashboard can also be served from **S3 + CloudFront** (cheaper, infinite scale). Keep a small Fargate service only if you need a live API (e.g. re-score on demand).

---

## Data & recommendation pipeline

```
index.html + data/jobs.json
        │
        ▼
┌───────────────────┐     Bolt via PrivateLink
│  parse_and_ingest │ ──────────────────────► Neo4j AuraDB (multi-AZ)
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ process_outliers  │  ATS score → outlier filter → top 5–10% band
└─────────┬─────────┘
          │ writes
          ▼
   s3://…/analysis.json
          │
          ▼
   CloudFront / Fargate static site
          │
          ▼  (optional later)
   Amazon Personalize Personalized-Ranking
   re-ranks the outlier candidate set using click/apply events
```

**Batch-first** (AWS guidance for recommendation systems): EventBridge + Step Functions run the pipeline on a schedule. Real-time path is only needed when interaction signals change relevance within minutes.

---

## High availability & failure modes

| Failure | Mitigation |
|---------|------------|
| Single AZ loss | ALB + Fargate multi-AZ; Aura multi-AZ; no single-AZ dependency |
| Task crash | ECS service replaces task; ALB drains unhealthy targets |
| Aura node failure | Aura managed failover; Bolt driver retries |
| Region failure | (Phase 2) Route 53 failover to secondary region + Aura multi-region or snapshot restore |
| Pipeline failure | Step Functions retries + SNS alarm; last good `analysis.json` remains on S3 |

RPO/RTO targets (single-region HA):
- **Serving path**: RTO minutes (task replacement), RPO = last successful pipeline run
- **Graph**: Aura automated backups + point-in-time; RPO minutes

---

## Security (minimum)

- Secrets Manager for Neo4j credentials (rotated); no plaintext in task defs
- IAM task role: `s3:GetObject/PutObject` on analysis bucket only; `secretsmanager:GetSecretValue`
- Execution role: ECR pull, CloudWatch Logs, Secrets
- ALB HTTPS only (ACM); redirect HTTP→HTTPS
- CloudFront WAF (optional) for bot / SQLi rules
- VPC Flow Logs + CloudWatch alarms on 5xx, task restarts, Step Functions failures

---

## Optional Amazon Personalize integration (phase 2)

Once you have interaction events (view / apply / dismiss):

1. Export `(user_id, item_id=job_id, event_type, timestamp)` to S3.
2. Train **Personalized-Ranking-v2** on the fixed candidate set of ATS outliers.
3. At request time: Lambda gets the deterministic outlier list → calls Personalize `GetPersonalizedRanking` → returns reordered list.
4. Keep the deterministic filter as a hard gate so critical skill gaps never appear.

This matches AWS “batch candidates + real-time re-rank” guidance without abandoning explainable ATS logic.

---

## Cost sketch (us-west-2, light traffic)

| Service | Approx. monthly |
|---------|-----------------|
| ECS Fargate 2×0.5 vCPU | ~$15–25 |
| ALB | ~$16 + LCU |
| Neo4j Aura Professional / Enterprise | see Neo4j pricing (dominant cost) |
| PrivateLink endpoints | ~$7–10 each + data |
| S3 + CloudFront | <$5 |
| Step Functions / EventBridge | cents |
| Secrets Manager | <$1 |

For a personal / low-traffic portfolio use case, **S3 + CloudFront static** + scheduled Fargate RunTask (no always-on service) is the most cost-efficient HA option while still multi-AZ for the batch path.

---

## Implementation order

1. Custom multi-AZ VPC + endpoints (this repo’s `terraform/` upgrade)
2. AuraDB + PrivateLink (Enterprise) or TLS public Bolt for Pro
3. ECR image + ECS service across 3 private subnets
4. ALB + ACM + Route 53
5. EventBridge → Step Functions → RunTask pipeline
6. S3 + CloudFront for static dashboard (optional split)
7. Observability (CloudWatch dashboards, alarms, X-Ray)
8. (Later) Personalize re-ranker when interaction data exists

# ats-neo4j-recommender

**AWS + Neo4j AuraDB recommendation system** that parses a live resume (`index.html`) into a weighted skill graph, ATS-scores job postings, and surfaces **strict outlier recommendations** — high-fit roles in the top 5–10% score band that miss only a few non-critical skills.

The static dashboard shows **only outlier job listings** (never perfect matches or critical-gap roles), ready for targeted upskilling.

---

## How it works

1. **Parse** (`scripts/common.py`) — reads `index.html` with BeautifulSoup. No hardcoded skills.
   - `.matrix-card` blocks become the skill tree (Origins / Gaming cards skipped).
   - `.cert-card` and `.tt-course` entries become credentials; keywords map them to skills.
   - `.timeline-item` entries become experience nodes linked to skills found in their text.
   - Skills mentioned only in prose count as weaker evidence (weight 0.6).

2. **Ingest** (`scripts/parse_and_ingest.py`) — writes the graph to Neo4j AuraDB:
   ```
   (Candidate)-[:HAS_SKILL {source,weight,evidence}]->(Skill)-[:IN_CATEGORY]->(Category)
   (Credential)-[:VALIDATES]->(Skill)
   (Experience)-[:USED]->(Skill)
   (Job)-[:REQUIRES {critical}]->(Skill)
   ```

3. **ATS score** (`scripts/process_outliers.py`) — weighted keyword coverage × 100.
   - Critical required skills count **double**.
   - Evidence weights: matrix/credential **1.0**, implied **0.8**, prose-only **0.6**.

4. **Recommend outliers** — roles where:
   - ATS score ≥ `--min-score` (default 55)
   - 1 … `--max-missing` (default 2) missing skills
   - **none** of the missing skills are critical
   - optionally restricted to the top **5–10%** score band among all scored jobs

5. **Dashboard** (`web/`) — glassmorphism static page that loads `analysis.json` and renders **strictly the outlier recommendations**.

---

## Repository layout

| Path | Purpose |
|------|---------|
| `index.html` | Source resume (parsed, never hardcoded) |
| `data/jobs.json` | Job postings with required skills + `critical` flag |
| `scripts/common.py` | Parse + score + percentile outlier selection |
| `scripts/parse_and_ingest.py` | Load graph into Neo4j |
| `scripts/process_outliers.py` | Score jobs, write `web/analysis.json` |
| `web/` | Recommendation dashboard (HTML / JS / CSS) |
| `docker/Dockerfile.app` | Ingest → score → serve on port 8080 |
| `terraform/` | ECS Fargate + ALB + Secrets Manager for AuraDB |
| `.env.example` | AuraDB connection variables |
| `build_zip.py` | Clean zip for GitHub / distribution |

---

## Run locally (no database)

```bash
pip install -r requirements.txt
python scripts/process_outliers.py --offline --min-score 55 --max-missing 2 --pct-low 5 --pct-high 10
cd web && python -m http.server 8080
# open http://localhost:8080
```

## Run with Neo4j AuraDB

```bash
cp .env.example .env   # fill NEO4J_URI / NEO4J_PASSWORD
set -a; source .env; set +a
python scripts/parse_and_ingest.py
python scripts/process_outliers.py --min-score 55 --max-missing 2 --pct-low 5 --pct-high 10
```

A local Neo4j works too:
```bash
docker run -d -p 7687:7687 -e NEO4J_AUTH=neo4j/changeme123 neo4j:5-community
```

---

## Deploy to AWS (ECS Fargate)

```bash
# 1. Create ECR repo and push image
aws ecr create-repository --repository-name ats-neo4j-recommender
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=us-west-2
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com
docker build -f docker/Dockerfile.app -t $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/ats-neo4j-recommender:latest .
docker push $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/ats-neo4j-recommender:latest

# 2. Terraform (AuraDB credentials go into Secrets Manager)
cd terraform && terraform init
terraform apply \
  -var "app_image=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/ats-neo4j-recommender:latest" \
  -var "neo4j_uri=neo4j+s://<dbid>.databases.neo4j.io" \
  -var "neo4j_password=<aura-password>"
```

Open the `dashboard_url` output. The Fargate task reaches AuraDB over TLS on the public internet. For private connectivity use AuraDB Virtual Dedicated Cloud + AWS PrivateLink. The ALB is HTTP-only by default (attach an ACM certificate for HTTPS).

---

## Updating job data

Replace `data/jobs.json` with real postings. Each entry needs:

```json
{
  "id": "j01",
  "title": "Role title",
  "company": "Company",
  "location": "Remote",
  "required": [
    { "skill": "AWS", "critical": true },
    { "skill": "Terraform", "critical": false }
  ]
}
```

Then re-run `process_outliers.py` (and `parse_and_ingest.py` if using Neo4j).

---

## Notes

- Images referenced by `index.html` are not required for parsing — only the HTML structure is used.
- The dashboard re-filters outliers client-side from the precomputed recommendations; sliders never surface non-outlier roles.
- Package for distribution: `python build_zip.py` → `dist/ats-neo4j-recommender.zip`.

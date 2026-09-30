/**
 * ATS Neo4j Recommendation dashboard.
 * Loads analysis.json and renders ONLY outlier job listings that pass the
 * current score / missing-skill thresholds (default top 5–10% band).
 */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const chip = (t, c) => `<span class="chip ${c}">${esc(t)}</span>`;

let data = null;

/** Outlier = score >= min, 1..max missing, no critical gaps. Never shows strict matches. */
function isOutlier(j, min, maxm) {
  if (!j.missing.length) return false;
  if (j.missing.some((m) => m.critical)) return false;
  return j.ats_score >= min && j.missing.length <= maxm;
}

function render() {
  const min = +$("ratio").value;
  const maxm = +$("maxm").value;
  $("rv").textContent = min;
  $("mv").textContent = maxm;

  const q = $("q").value.toLowerCase();
  const co = $("company").value;

  // Prefer the pre-filtered recommendations array; re-apply live thresholds
  const pool = (data.recommendations && data.recommendations.length)
    ? data.recommendations
    : data.jobs.filter((j) => j.outlier);

  const shown = pool
    .filter((j) => isOutlier(j, min, maxm))
    .filter((j) => (!co || j.company === co) && `${j.title} ${j.company}`.toLowerCase().includes(q))
    .sort((a, b) => b.ats_score - a.ats_score);

  $("sRec").textContent = shown.length;
  $("sBest").textContent = shown.length
    ? Math.max(...shown.map((j) => j.ats_score)).toFixed(0)
    : Math.max(...data.jobs.map((j) => j.ats_score), 0).toFixed(0);

  const band = data.thresholds || {};
  $("sBand").textContent = `${band.pct_low ?? 5}–${band.pct_high ?? 10}%`;

  $("jobs").innerHTML = shown.length
    ? shown
        .map(
          (j) => `<article class="card">
      <div class="card-top">
        <span class="tag">Outlier recommendation · ${esc(j.location || "n/a")}</span>
        <span class="score-pill">${j.ats_score}<small>/100</small></span>
      </div>
      <h3>${esc(j.title)}</h3>
      <div class="co">${esc(j.company)}</div>
      <div class="bar"><i style="width:${j.ats_score}%"></i></div>
      <div class="chips">
        ${j.matched.map((m) => chip(m.skill, m.weight < 1 ? "soft" : "ok")).join("")}
        ${j.missing.map((m) => chip("gap: " + m.skill, m.critical ? "bad" : "warn")).join("")}
      </div>
      <p class="hint">${j.missing.length} non-critical skill${j.missing.length === 1 ? "" : "s"} to close</p>
    </article>`
        )
        .join("")
    : `<p class="empty">No outlier recommendations match the current filters. Lower the minimum ATS score or raise max missing skills.</p>`;
}

function renderTree() {
  const groups = {};
  data.skills.forEach((s) => (groups[s.category] ||= []).push(s));
  $("tree").innerHTML = Object.entries(groups)
    .map(
      ([cat, list]) =>
        `<details>
          <summary>${esc(cat)} <span class="count">${list.length}</span></summary>
          <div class="chips">${list
            .map((s) =>
              chip(
                s.name + (s.evidence ? ` ·${s.evidence}` : ""),
                s.source === "text" || s.source === "implied" ? "soft" : ""
              )
            )
            .join("")}</div>
        </details>`
    )
    .join("");
}

async function init() {
  try {
    data = await fetch("analysis.json").then((r) => {
      if (!r.ok) throw new Error("missing analysis.json");
      return r.json();
    });
    $("who").textContent = `${data.candidate} · scored via ${data.source} · ${data.generated.slice(0, 10)}`;
    $("sSkills").textContent = data.skills.length;
    if (data.thresholds) {
      $("ratio").value = data.thresholds.min_score ?? 55;
      $("maxm").value = data.thresholds.max_missing ?? 2;
    }
    [...new Set(data.jobs.map((j) => j.company))]
      .sort()
      .forEach((c) => $("company").add(new Option(c, c)));
    ["q", "company", "ratio", "maxm"].forEach((id) => $(id).addEventListener("input", render));
    renderTree();
    render();
  } catch (e) {
    $("who").textContent =
      "Could not load analysis.json. Run: python scripts/process_outliers.py --offline  then serve the web/ folder.";
  }
}
init();

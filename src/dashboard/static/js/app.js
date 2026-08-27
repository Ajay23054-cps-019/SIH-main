/* SAT-SA dashboard logic — vanilla JS, no build step.
 *
 * Pages are thin Jinja2 shells; everything below renders client-side by
 * fetching the same REST API an auditor would call, so the dashboard can
 * never display a number that did not come through the documented API.
 *
 * Chart.js is bundled locally (offline requirement); every chart has a
 * pure-CSS fallback when window.Chart is unavailable.
 */
"use strict";

// ---------------------------------------------------------------- helpers

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

async function fetchJSON(url, options) {
  const resp = await fetch(url, options);
  let body = null;
  try { body = await resp.json(); } catch (err) { /* non-JSON */ }
  if (!resp.ok) {
    const detail = body && body.errors && body.errors[0]
      ? body.errors[0].detail : resp.status + " " + resp.statusText;
    throw new Error(detail);
  }
  if (body && body.meta && body.meta.generated_at) {
    const el = document.getElementById("data-freshness");
    if (el) el.textContent = "API data generated at " +
      new Date(body.meta.generated_at).toLocaleString();
  }
  return body;
}

function sevClass(severity) {
  return "badge " + String(severity || "").toLowerCase();
}
function sevBadge(severity) {
  if (!severity) return "";
  return '<span class="' + sevClass(severity) + '">' +
    escapeHtml(severity) + "</span>";
}

function fmtNumber(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "–";
  const n = Number(v);
  if (Math.abs(n) >= 1000) return n.toLocaleString(undefined,
    { maximumFractionDigits: 1 });
  if (Math.abs(n) >= 10) return n.toFixed(1);
  return n.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function setError(el, message) {
  el.innerHTML = '<span class="missing-note">Could not load data: ' +
    escapeHtml(message) + "</span>";
}

// ------------------------------------------------------- page dispatching

document.addEventListener("DOMContentLoaded", function () {
  const path = window.location.pathname;
  if (/^\/dashboard\/?$/.test(path)) initPortfolio();
  else if (/^\/dashboard\/entity\/.+/.test(path)) {
    initEntity(decodeURIComponent(path.split("/")[3]));
  } else if (/^\/dashboard\/finding\/.+/.test(path)) {
    initFinding(decodeURIComponent(path.replace(/^\/dashboard\/finding\//, "")));
  }
});

// ------------------------------------------------------------- portfolio

function initPortfolio() {
  renderSummary();
  renderRankings();
  initUpload();
}

function initUpload() {
  const form = document.getElementById("upload-form");
  const status = document.getElementById("upload-status");
  if (!form) return;

  form.addEventListener("submit", async function (ev) {
    ev.preventDefault();
    const entity = document.getElementById("upload-entity").value;
    const format = document.getElementById("upload-format").value;
    const fileInput = document.getElementById("upload-file");
    const file = fileInput.files[0];
    if (!file) {
      status.innerHTML = '<span class="error">Please select a file first.</span>';
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("entity", entity);
    fd.append("format", format);
    status.innerHTML = '<span class="muted">Uploading ' + escapeHtml(file.name) + '...</span>';
    try {
      const resp = await fetch("/api/ingest/upload", { method: "POST", body: fd });
      const body = await resp.json();
      if (resp.ok && body.data) {
        const d = body.data;
        status.innerHTML = '<span class="success">Uploaded ' +
          escapeHtml(file.name) + ': ' + d.records_ingested + ' records ingested' +
          (d.quality_score != null ? ' (quality: ' + Math.round(d.quality_score * 100) + '%)' : '') +
          '. <a href="#" onclick="location.reload(); return false;">Refresh dashboard</a></span>';
      } else {
        const err = body.errors && body.errors[0] ? body.errors[0].detail : 'Upload failed';
        status.innerHTML = '<span class="error">' + escapeHtml(err) + '</span>';
      }
    } catch (err) {
      status.innerHTML = '<span class="error">Upload failed: ' + escapeHtml(err.message) + '</span>';
    }
  });
}

async function renderSummary() {
  const elHigh = document.getElementById("high-priority");
  const elCrit = document.getElementById("critical-signals");
  try {
    const body = await fetchJSON("/api/portfolio/summary");
    const d = body.data;
    // Total CSEs is filled by renderRankings (it knows the full list).
    const high = d.findings_by_severity && d.findings_by_severity.HIGH || 0;
    elHigh.textContent = high;
    const critTypes = await fetchJSON("/api/findings?severity=HIGH");
    elCrit.textContent = new Set(
      critTypes.data.map(function (f) { return f.signal_type; })).size;
  } catch (err) {
    elHigh.textContent = "!"; elCrit.textContent = "!";
    console.error(err);
  }
}

async function renderRankings() {
  const tbody = document.getElementById("rankings-body");
  try {
    const body = await fetchJSON("/api/portfolio/rankings");
    const rows = body.data;
    const elTotal = document.getElementById("total-cses");
    if (elTotal) elTotal.textContent = rows.length;

    const maxP = Math.max.apply(null, rows.map(function (r) {
      return r.priority; }).concat([0])) || 1;

    const fbResp = await fetchJSON("/api/feedback/summary");
    const fbBySignal = {};
    (fbResp.data || []).forEach(function (s) { fbBySignal[s.signal_type] = s; });
    const fbTotal = (fbResp.data || []).reduce(function (a, s) {
      return a + s.n_feedback; }, 0);

    tbody.innerHTML = rows.map(function (r, i) {
      const sector = r.sector || "–";
      const sizeBand = r.size_band ? " · " + escapeHtml(r.size_band) : "";
      const barW = Math.max(2, Math.round(100 * r.priority / maxP));
      const signal = r.top_signal
        ? sevBadge(r.top_signal_severity) + " <code>" +
          escapeHtml(r.top_signal) + "</code>"
        : '<span class="muted">none</span>';
      const fb = r.top_signal && fbBySignal[r.top_signal];
      const fbCell = fb
        ? '<span class="fb-pill" title="' +
          escapeHtml([fb.worthwhile + ' worthwhile',
                      fb.not_worthwhile + ' not worthwhile',
                      fb.uncertain + ' uncertain'].join(', ')) + '">' +
          fb.n_feedback + '×</span>'
        : '<span class="muted fb-pill fb-pill-empty">–</span>';
      return '<tr tabindex="0" data-cse="' + escapeHtml(r.cse_id) + '">' +
        "<td>" + (i + 1) + "</td>" +
        "<td><strong>" + escapeHtml(r.cse_id) + "</strong></td>" +
        "<td>" + sector + sizeBand + "</td>" +
        '<td class="num"><span class="priority-bar" style="width:' +
          barW + 'px"></span>' + r.priority.toFixed(1) + "</td>" +
        '<td class="num">' + r.n_findings + "</td>" +
        "<td>" + signal + "</td>" +
        '<td class="num">' + fbCell + "</td></tr>";
    }).join("");

    tbody.addEventListener("click", function (ev) {
      const tr = ev.target.closest("tr[data-cse]");
      if (tr) window.location.href =
        "/dashboard/entity/" + encodeURIComponent(tr.dataset.cse);
    });
    tbody.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter") return;
      const tr = ev.target.closest("tr[data-cse]");
      if (tr) window.location.href =
        "/dashboard/entity/" + encodeURIComponent(tr.dataset.cse);
    });

    renderFeedbackSummary(fbResp.data || [], fbTotal);
  } catch (err) {
    setError(tbody, err.message);
  }
}

function renderFeedbackSummary(summary, total) {
  const panel = document.getElementById("feedback-summary-panel");
  const body = document.getElementById("feedback-summary-body");
  if (!panel || !body) return;
  if (!summary.length) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const advisories = summary.filter(function (s) { return s.advisory; });
  body.innerHTML =
    '<p class="muted">' + total + ' dispositions recorded across ' +
    summary.length + ' signal types.</p>' +
    (advisories.length
      ? '<table class="feedback-table"><thead><tr><th>Signal</th>' +
        '<th>Worthwhile</th><th>Not</th><th>Uncertain</th>' +
        '<th>Rate</th><th>Advisory</th></tr></thead><tbody>' +
        advisories.map(function (s) {
          return '<tr><td><code>' + escapeHtml(s.signal_type) + '</code></td>' +
            '<td class="num">' + s.worthwhile + '</td>' +
            '<td class="num">' + s.not_worthwhile + '</td>' +
            '<td class="num">' + s.uncertain + '</td>' +
            '<td class="num">' + Math.round(s.worthwhile_rate * 100) + '%</td>' +
            '<td><span class="advisory">' + escapeHtml(s.advisory) +
            '</span></td></tr>';
        }).join("") + '</tbody></table>'
      : '<p class="muted">No advisories yet — keep recording dispositions ' +
        'to surface calibration guidance.</p>');
}

// ---------------------------------------------------------------- entity

function initEntity(cseId) {
  document.getElementById("entity-title").textContent = cseId;
  loadCase(cseId);
  loadProfile(cseId);
  loadFindings(cseId);
  loadPeers(cseId);
}

// Fused supervisory case (signal fusion): shown only when this CSE's
// findings cleared the fusion gates in the last pipeline run.
async function loadCase(cseId) {
  const el = document.getElementById("case-banner");
  if (!el) return;
  try {
    const body = await fetchJSON("/api/cases?cse_id=" +
      encodeURIComponent(cseId));
    if (!body.data.length) { el.hidden = true; return; }
    const c = body.data[0];
    const members = c.finding_ids.map(function (fid) {
      const sig = fid.split(":")[1] || fid;
      return '<a class="case-member" href="/dashboard/finding/' +
        encodeURIComponent(fid) + '"><code>' + escapeHtml(sig) +
        "</code></a>";
    }).join(" ");
    el.innerHTML =
      "<h2>Supervisory Case <code>" + escapeHtml(c.case_id) + "</code> " +
      sevBadge(c.severity) + " <span class=\"finding-meta\">joint " +
      "confidence " + fmtNumber(c.joint_confidence) + " &middot; " +
      escapeHtml(String(c.n_findings)) + " findings</span></h2>" +
      '<p class="case-narrative">' + escapeHtml(c.narrative) + "</p>" +
      '<p class="case-members">Member findings: ' + members + "</p>" +
      '<p class="finding-meta">' + c.caveats.map(escapeHtml).join(" ") +
      "</p>";
    el.hidden = false;
  } catch (err) { el.hidden = true; /* no cases table / no case */ }
}

async function loadProfile(cseId) {
  const attrsEl = document.getElementById("entity-attrs");
  try {
    const body = await fetchJSON("/api/profiles/" + encodeURIComponent(cseId));
    const prof = body.data.filter(function (p) { return p.period === "ALL"; })
      .concat(body.data)[0];
    if (!prof) throw new Error("no ALL-period profile stored");

    ["alert_volume_total", "inv_depth_mean", "closure_velocity_median_h",
      "esc_rate"].forEach(function (key) {
      const cell = document.getElementById("m-" + key);
      if (cell) cell.textContent = fmtNumber(prof.metrics[key]);
    });
  } catch (err) {
    document.querySelectorAll(".card-value[id^='m-']").forEach(function (el) {
      el.textContent = "!";
    });
    console.error(err);
  }

  // Sector/size context straight from the metadata table via ingest status
  // is not exposed per-CSE; the peers endpoint carries it instead.
  try {
    const bench = await fetchJSON("/api/peers/" + encodeURIComponent(cseId));
    const d = bench.data;
    attrsEl.innerHTML = escapeHtml(d.sector || "Unknown sector") +
      " &middot; " + escapeHtml(d.size_band || "Unknown size band") +
      " &middot; peer group: <strong>" + escapeHtml(d.group_label) +
      "</strong> (" + d.peer_ids.length + " peers)";
  } catch (err) { /* peer load reports its own errors */ }
}

function actionsHtml(finding) {
  const acts = finding.recommended_actions || [];
  if (!acts.length) return "";
  return "<ul>" + acts.map(function (a) {
    return "<li>" + escapeHtml(a) + "</li>"; }).join("") + "</ul>";
}

async function loadFindings(cseId) {
  const list = document.getElementById("findings-list");
  try {
    const body = await fetchJSON("/api/findings?cse_id=" +
      encodeURIComponent(cseId));
    const rows = body.data;
    if (!rows.length) {
      list.innerHTML = '<li class="muted">No signals fired for this CSE in ' +
        "the current run.</li>";
      setActions([], "No signals fired — nothing to act on this cycle.");
      return;
    }
    list.innerHTML = rows.map(function (f) {
      return "<li>" + sevBadge(f.severity) + " <code>" +
        escapeHtml(f.signal_type) + "</code> " +
        '<span class="finding-meta">confidence ' + fmtNumber(f.confidence) +
        " &middot; period " + escapeHtml(f.period) + "</span><br>" +
        '<a href="/dashboard/finding/' + encodeURIComponent(f.finding_id) +
        '">Open evidence chain &rarr;</a>' +
        (f.recommended_actions && f.recommended_actions.length
          ? actionsHtml(f) : "") + "</li>";
    }).join("");
    // Consolidated examiner actions across this CSE's findings (deduped,
    // most serious finding first — rows arrive severity-sorted).
    const seen = {};
    const consolidated = [];
    rows.forEach(function (f) {
      (f.recommended_actions || []).forEach(function (a) {
        if (!seen[a]) { seen[a] = true; consolidated.push(a); }
      });
    });
    setActions(consolidated);
  } catch (err) {
    setError(list, err.message);
  }
}

function setActions(actions, emptyMessage) {
  const el = document.getElementById("actions-list");
  if (!el) return;
  el.innerHTML = actions.length
    ? actions.map(function (a) {
        return "<li>" + escapeHtml(a) + "</li>"; }).join("")
    : '<li class="muted">' +
      escapeHtml(emptyMessage || "None recorded.") + "</li>";
}

const PEER_CHART_METRIC = "inv_depth_mean";

async function loadPeers(cseId) {
  const note = document.getElementById("peer-group-note");
  const bars = document.getElementById("peer-bars");
  const canvas = document.getElementById("peer-chart");
  try {
    const body = await fetchJSON("/api/peers/" + encodeURIComponent(cseId));
    const d = body.data;
    if (!d.benchmarks.length) {
      note.textContent = d.skipped && d.skipped.__all__
        ? d.skipped.__all__ : "No comparable-metric benchmarks stored.";
      canvas.hidden = true;
      return;
    }
    const bm = d.benchmarks.filter(function (b) {
      return b.metric === PEER_CHART_METRIC; })[0] || d.benchmarks[0];
    note.textContent = bm.metric + " vs peer mean (" + fmtNumber(bm.peer_mean) +
      ") over " + bm.n_peers + " peers — z " + fmtNumber(bm.z_score) +
      ", percentile " + fmtNumber(bm.percentile) + "." +
      (bm.note ? " Note: " + bm.note : "");

    // Peer member values are not stored individually — plot the CSE against
    // the distribution stats we do hold (self / peer mean / peer median).
    const labels = ["This CSE", "Peer median", "Peer mean"];
    const values = [bm.value, bm.peer_median, bm.peer_mean];

    if (window.Chart) {           // bundled Chart.js — offline-safe
      bars.hidden = true;
      canvas.hidden = false;
      new Chart(canvas, {
        type: "bar",
        data: { labels: labels, datasets: [{
          label: bm.metric, data: values,
          backgroundColor: ["#14532d", "#93c5ae", "#93c5ae"],
        }] },
        options: {
          responsive: true, animation: false,
          plugins: { legend: { display: false },
            title: { display: true, text: bm.metric } },
          scales: { y: { beginAtZero: true } },
        },
      });
    } else {                      // pure-CSS fallback, no JS chart lib
      canvas.hidden = true;
      const maxV = Math.max.apply(null, values.concat([1]));
      bars.innerHTML = labels.map(function (label, i) {
        const h = Math.max(2, Math.round(200 * values[i] / maxV));
        return '<div class="pbar-col' + (i === 0 ? " self" : "") + '">' +
          '<div class="pbar' + (i === 0 ? " self" : "") +
          '" style="height:' + h + 'px"></div>' +
          '<div class="pbar-label">' + escapeHtml(label) + ": " +
          fmtNumber(values[i]) + "</div></div>";
      }).join("");
    }
  } catch (err) {
    note.textContent = "Peer comparison unavailable.";
    canvas.hidden = true;
    setError(bars, err.message);
  }
}

// ---------------------------------------------------------------- finding

function initFinding(findingId) {
  loadFinding(findingId);
  initFeedback(findingId);
}

// ------------------------------------------------------- examiner feedback

function initFeedback(findingId) {
  const buttons = document.querySelectorAll("#feedback-buttons .fb-btn");
  const state = document.getElementById("feedback-state");
  if (!buttons.length || !state) return;

  async function refresh() {
    try {
      const body = await fetchJSON("/api/findings/" +
        encodeURIComponent(findingId) + "/feedback");
      const row = body.data;
      buttons.forEach(function (b) {
        b.classList.toggle("active",
          !!row && b.dataset.disposition === row.disposition);
      });
      state.textContent = row
        ? "Recorded: " + row.disposition + " (" + row.updated_at + ")" +
          (row.examiner ? " — " + row.examiner : "")
        : "No disposition recorded yet.";
    } catch (err) {
      state.textContent = "Feedback unavailable: " + err.message;
    }
  }

  buttons.forEach(function (b) {
    b.addEventListener("click", async function () {
      state.textContent = "Saving…";
      try {
        await fetchJSON("/api/findings/" +
          encodeURIComponent(findingId) + "/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ disposition: b.dataset.disposition }),
        });
      } catch (err) { /* refresh() surfaces the failure */ }
      refresh();
    });
  });
  refresh();
}

function detailRow(record) {
  const json = JSON.stringify(record.key_fields, null, 2) || "{}";
  return '<tr class="record-detail" hidden><td colspan="4"><pre>' +
    escapeHtml(json) + "</pre></td></tr>";
}

async function loadFinding(findingId) {
  const title = document.getElementById("finding-title");
  try {
    const body = await fetchJSON("/api/findings/" +
      encodeURIComponent(findingId) + "/explain");
    const f = body.data.finding;
    const chain = body.data.chain;

    title.textContent = f.signal_type;
    document.title = f.signal_type + " · SAT-SA";
    const sevEl = document.getElementById("finding-severity");
    sevEl.className = sevClass(f.severity);
    sevEl.textContent = f.severity;
    document.getElementById("finding-confidence").textContent =
      fmtNumber(f.confidence);
    document.getElementById("finding-category").textContent =
      f.signal_category;
    document.getElementById("finding-period").textContent = f.period;
    document.querySelector(".breadcrumb").innerHTML =
      '<a href="/dashboard/entity/' + encodeURIComponent(f.cse_id) +
      '">&larr; ' + escapeHtml(f.cse_id) + "</a>";

    // Rationale = detection logic + standard caveat(s)
    const rationale = document.getElementById("rationale");
    rationale.classList.remove("loading");
    rationale.textContent = f.detection_logic ||
      "(detection logic not recorded)";
    document.getElementById("caveats").innerHTML =
      (f.caveats || []).map(function (c) {
        return "<li>" + escapeHtml(c) + "</li>"; }).join("");

    // Chain metrics (Signal → Metric level of the trace)
    if (chain) {
      document.getElementById("chain-metrics").innerHTML =
        chain.metrics.map(function (m) {
          return '<div class="chain-step"><span class="step-tag">' +
            escapeHtml(m.metric_name) + "</span><code>" +
            escapeHtml(m.calculation) + "</code> = <strong>" +
            fmtNumber(m.value) + "</strong></div>";
        }).join("") +
        '<div class="chain-step"><span class="step-tag">logic</span>' +
        escapeHtml(chain.detection_logic) + "</div>";

      const tbody = document.getElementById("evidence-body");
      tbody.innerHTML = chain.records.length
        ? chain.records.map(function (r) {
            const rec = { record_type: r.record_type, record_id: r.record_id,
              key_fields: r.key_fields };
            return '<tr class="expandable" data-rec=\'' +
              escapeHtml(JSON.stringify(rec)) + "'><td><code>" +
              escapeHtml(r.record_id) + "</code></td><td>" +
              escapeHtml(r.record_type) + "</td><td>" +
              Object.keys(r.key_fields || {}).map(function (k) {
                return k + "=" + String(r.key_fields[k]);
              }).join(", ") + "</td><td>" + escapeHtml(r.relevance) +
              "</td></tr>" + detailRow(r);
          }).join("")
        : '<tr><td colspan="4" class="muted">No individual records were ' +
          "attached to this finding (metric-level signal).</td></tr>";

      document.getElementById("missing-records").innerHTML =
        chain.missing_records.map(function (m) {
          return '<p class="missing-note">Referenced record not found: ' +
            "<code>" + escapeHtml(m.record_id) + "</code> — " +
            escapeHtml(m.note) + "</p>";
        }).join("");

      // Expandable record detail rows
      tbody.addEventListener("click", function (ev) {
        const tr = ev.target.closest("tr.expandable");
        if (!tr) return;
        const det = tr.nextElementSibling;
        if (det) det.hidden = !det.hidden;
      });
    }

    // Recommended examiner actions
    setActions(f.recommended_actions || []);

    // Optional LLM narrative — always clearly labeled when present.
    if (body.data.narrative) {
      const panel = document.createElement("section");
      panel.className = "panel";
      panel.style.borderLeft = "4px solid var(--medium)";
      panel.innerHTML = "<h2>Generated Narrative</h2><p class='muted'>" +
        escapeHtml(body.data.narrative.label) + "</p><p>" +
        escapeHtml(body.data.narrative.explanation).replace(/\n/g, "<br>") +
        "</p>" + ((body.data.narrative.questions || []).length
          ? "<ul>" + body.data.narrative.questions.map(function (q) {
              return "<li>" + escapeHtml(q) + "</li>"; }).join("") +
            "</ul>" : "");
      document.querySelector(".container").appendChild(panel);
    }

    loadFindingPeerContext(f);
  } catch (err) {
    setError(document.getElementById("rationale"), err.message);
  }
}

async function loadFindingPeerContext(finding) {
  const panel = document.getElementById("peer-context-panel");
  const box = document.getElementById("peer-context");
  try {
    const body = await fetchJSON("/api/peers/" +
      encodeURIComponent(finding.cse_id));
    const d = body.data;
    if (!d.benchmarks.length) return;   // keep panel hidden
    const outliers = d.benchmarks.filter(function (b) {
      return b.is_outlier; });
    panel.hidden = false;
    box.innerHTML = "<p class='muted'>" + escapeHtml(d.group_label) +
      " — " + escapeHtml(d.group_definition) + "</p>" +
      (outliers.length
        ? "<ul>" + outliers.map(function (b) {
            return "<li><code>" + escapeHtml(b.metric) + "</code>: " +
              fmtNumber(b.value) + " vs peers " + fmtNumber(b.peer_mean) +
              " (z " + fmtNumber(b.z_score) + ")</li>";
          }).join("") + "</ul>"
        : "<p class='muted'>No metric flagged as a peer outlier.</p>");
  } catch (err) { /* peer context is best-effort */ }
}

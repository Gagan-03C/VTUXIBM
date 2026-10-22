/**
 * QuantumFlow — Dashboard Controller
 * static/dashboard.js  ·  Owner: Frontend Engineer
 *
 * Connects frontend UI to real Flask endpoints:
 *   - GET  /api/traffic
 *   - POST /api/traffic
 *   - POST /api/optimize/baseline
 *   - POST /api/optimize/responsive
 *   - POST /api/optimize/qaoa
 *   - GET  /api/results
 *
 * Rules:
 *   - NO hardcoded fake results.
 *   - NO traffic calculations in JavaScript (all metrics come from backend).
 *   - Defensive error handling with readable banners.
 */

document.addEventListener("DOMContentLoaded", () => {
  // -------------------------------------------------------------------------
  // DOM Element References
  // -------------------------------------------------------------------------
  const intersections = ["A", "B", "C", "D"];

  // Header & Banner
  const headerTotalVehicles = document.getElementById("header-total-vehicles");
  const statusBanner = document.getElementById("status-banner");
  const bannerMessage = document.getElementById("banner-message");
  const bannerIcon = document.getElementById("banner-icon");
  const btnBannerClose = document.getElementById("btn-banner-close");

  // Traffic & Scenario Buttons
  const scenarioButtons = document.querySelectorAll(".scenario-btn");
  const btnApplyTraffic = document.getElementById("btn-apply-traffic");
  const btnRefreshTraffic = document.getElementById("btn-refresh-traffic");
  const trafficSyncStatus = document.getElementById("traffic-sync-status");

  // Optimization Buttons
  const btnOptBaseline = document.getElementById("btn-optimize-baseline");
  const btnOptResponsive = document.getElementById("btn-optimize-responsive");
  const btnOptQAOA = document.getElementById("btn-optimize-qaoa");

  // QAOA Advanced Tuning
  const selectQAOAP = document.getElementById("select-qaoa-p");
  const selectQAOAShots = document.getElementById("select-qaoa-shots");
  const inputQAOAMaxiter = document.getElementById("input-qaoa-maxiter");
  const inputQAOASeed = document.getElementById("input-qaoa-seed");

  // KPI Elements
  const activeAlgoName = document.getElementById("active-algo-name");
  const activeAlgoStatus = document.getElementById("active-algo-status");
  const bitstringWrapper = document.getElementById("bitstring-display-wrapper");
  const displayMeasuredBitstring = document.getElementById("display-measured-bitstring");

  const kpiTotalVehicles = document.getElementById("kpi-total-vehicles");
  const kpiVehiclesServed = document.getElementById("kpi-vehicles-served");
  const kpiRemainingQueue = document.getElementById("kpi-remaining-queue");
  const kpiTotalDelay = document.getElementById("kpi-total-delay");
  const kpiAvgWait = document.getElementById("kpi-avg-wait");
  const kpiDelayReduction = document.getElementById("kpi-delay-reduction");
  const kpiDelayReductionCaption = document.getElementById("kpi-delay-reduction-caption");
  const kpiRuntime = document.getElementById("kpi-runtime");

  // History Log Table
  const tableResultsBody = document.getElementById("table-results-body");
  const btnRefreshHistory = document.getElementById("btn-refresh-history");

  // -------------------------------------------------------------------------
  // Notification Banner Helpers
  // -------------------------------------------------------------------------
  function showBanner(message, type = "info") {
    statusBanner.className = `status-banner banner-${type}`;
    bannerMessage.textContent = message;

    if (type === "success") bannerIcon.textContent = "✓";
    else if (type === "error") bannerIcon.textContent = "⚠";
    else bannerIcon.textContent = "ℹ";

    statusBanner.classList.remove("hidden");
  }

  function hideBanner() {
    statusBanner.classList.add("hidden");
  }

  if (btnBannerClose) {
    btnBannerClose.addEventListener("click", hideBanner);
  }

  // -------------------------------------------------------------------------
  // Loading State Helper
  // -------------------------------------------------------------------------
  function setButtonLoading(button, isLoading, loadingText = "Running...") {
    const textSpan = button.querySelector(".btn-text");
    const spinner = button.querySelector(".btn-spinner");

    if (isLoading) {
      button.disabled = true;
      if (textSpan) textSpan.dataset.originalText = textSpan.textContent;
      if (textSpan) textSpan.textContent = loadingText;
      if (spinner) spinner.classList.remove("hidden");
    } else {
      button.disabled = false;
      if (textSpan && textSpan.dataset.originalText) {
        textSpan.textContent = textSpan.dataset.originalText;
      }
      if (spinner) spinner.classList.add("hidden");
    }
  }

  // -------------------------------------------------------------------------
  // Fetch & Render Traffic State
  // -------------------------------------------------------------------------
  async function loadTrafficState() {
    try {
      trafficSyncStatus.textContent = "Fetching traffic snapshot...";
      const res = await fetch("/api/traffic");
      const data = await res.json();

      if (!res.ok || data.status !== "ok") {
        throw new Error(data.message || `Server error (${res.status})`);
      }

      renderTrafficInputs(data.traffic_input);
      if (headerTotalVehicles) {
        headerTotalVehicles.textContent = `${data.total_vehicles || 0} veh`;
      }
      trafficSyncStatus.textContent = "Synchronized with backend traffic snapshot.";
    } catch (err) {
      showBanner(`Failed to load traffic state: ${err.message}`, "error");
      trafficSyncStatus.textContent = "Synchronization error.";
    }
  }

  function renderTrafficInputs(trafficInput) {
    if (!trafficInput) return;

    intersections.forEach((iid) => {
      const counts = trafficInput[iid] || trafficInput[`(${iid})`];
      if (!counts) return;

      const inputNS = document.getElementById(`input-ns-${iid}`);
      const inputEW = document.getElementById(`input-ew-${iid}`);

      if (inputNS) inputNS.value = counts.ns_count;
      if (inputEW) inputEW.value = counts.ew_count;
    });
  }

  // -------------------------------------------------------------------------
  // Apply Custom Queue Counts (POST /api/traffic)
  // -------------------------------------------------------------------------
  async function applyCustomTraffic() {
    hideBanner();
    const trafficInput = {};

    intersections.forEach((iid) => {
      const nsVal = parseInt(document.getElementById(`input-ns-${iid}`)?.value || "0", 10);
      const ewVal = parseInt(document.getElementById(`input-ew-${iid}`)?.value || "0", 10);
      trafficInput[iid] = {
        ns_count: isNaN(nsVal) ? 0 : Math.max(0, nsVal),
        ew_count: isNaN(ewVal) ? 0 : Math.max(0, ewVal),
      };
    });

    try {
      btnApplyTraffic.disabled = true;
      trafficSyncStatus.textContent = "Applying queue counts...";

      const res = await fetch("/api/traffic", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ traffic_input: trafficInput }),
      });
      const data = await res.json();

      if (!res.ok || data.status !== "ok") {
        throw new Error(data.message || `Failed to update traffic (${res.status})`);
      }

      if (headerTotalVehicles) {
        headerTotalVehicles.textContent = `${data.total_vehicles || 0} veh`;
      }
      showBanner(`Traffic queues successfully updated (${data.total_vehicles} total vehicles).`, "success");
      trafficSyncStatus.textContent = "Custom queues applied.";

      // Clear scenario button active states
      scenarioButtons.forEach((b) => b.classList.remove("active"));
    } catch (err) {
      showBanner(`Error updating traffic queues: ${err.message}`, "error");
      trafficSyncStatus.textContent = "Error applying queues.";
    } finally {
      btnApplyTraffic.disabled = false;
    }
  }

  // -------------------------------------------------------------------------
  // Preset Scenario Handler (POST /api/traffic with scenario)
  // -------------------------------------------------------------------------
  async function loadScenario(scenarioName, buttonEl) {
    hideBanner();
    try {
      scenarioButtons.forEach((b) => b.classList.remove("active"));
      if (buttonEl) buttonEl.classList.add("active");

      trafficSyncStatus.textContent = `Generating ${scenarioName} scenario...`;

      let payload = {};
      if (scenarioName === "benchmark") {
        // Benchmark initial snapshot
        payload = {
          traffic_input: {
            A: { ns_count: 45, ew_count: 12 },
            B: { ns_count: 30, ew_count: 20 },
            C: { ns_count: 10, ew_count: 40 },
            D: { ns_count: 25, ew_count: 15 },
          },
        };
      } else {
        payload = { scenario: scenarioName, seed: 42 };
      }

      const res = await fetch("/api/traffic", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (!res.ok || data.status !== "ok") {
        throw new Error(data.message || `Failed to set scenario (${res.status})`);
      }

      renderTrafficInputs(data.traffic_input);
      if (headerTotalVehicles) {
        headerTotalVehicles.textContent = `${data.total_vehicles || 0} veh`;
      }
      showBanner(`Scenario '${scenarioName}' loaded (${data.total_vehicles} vehicles).`, "info");
      trafficSyncStatus.textContent = `Active scenario: ${scenarioName}`;
    } catch (err) {
      showBanner(`Error loading scenario: ${err.message}`, "error");
      trafficSyncStatus.textContent = "Failed to load scenario.";
    }
  }

  // -------------------------------------------------------------------------
  // Optimization Dispatchers
  // -------------------------------------------------------------------------
  async function runOptimization(endpoint, buttonEl, payload = {}) {
    hideBanner();
    setButtonLoading(buttonEl, true);

    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (!res.ok || data.status !== "ok") {
        throw new Error(data.message || `Solver execution failed (${res.status})`);
      }

      renderSolverResult(data);
      showBanner(`Optimization complete: ${data.algorithm} (${data.solver_status || "ok"}).`, "success");
      loadResultsHistory();
    } catch (err) {
      showBanner(`Optimization Error: ${err.message}`, "error");
    } finally {
      setButtonLoading(buttonEl, false);
    }
  }

  // -------------------------------------------------------------------------
  // Render Solver Results & Metrics to UI
  // -------------------------------------------------------------------------
  function renderSolverResult(data) {
    if (!data) return;

    // Algorithm & Status Badges
    const algoName = data.algorithm || "unknown";
    if (activeAlgoName) activeAlgoName.textContent = formatAlgorithmName(algoName);

    const status = data.solver_status || data.status || "ok";
    if (activeAlgoStatus) {
      activeAlgoStatus.textContent = status;
      activeAlgoStatus.className = `status-badge status-${status}`;
    }

    // QAOA Bitstring
    if (bitstringWrapper) {
      if (data.bitstring) {
        bitstringWrapper.classList.remove("hidden");
        if (displayMeasuredBitstring) displayMeasuredBitstring.textContent = data.bitstring;
      } else {
        bitstringWrapper.classList.add("hidden");
      }
    }

    // Metrics KPIs
    const m = data.metrics || {};
    if (kpiTotalVehicles) kpiTotalVehicles.textContent = m.total_vehicles ?? "--";
    if (kpiVehiclesServed) kpiVehiclesServed.textContent = m.vehicles_served ?? "--";
    if (kpiRemainingQueue) kpiRemainingQueue.textContent = m.remaining_queue ?? "--";
    if (kpiTotalDelay) kpiTotalDelay.textContent = m.total_delay_sec !== undefined ? `${m.total_delay_sec.toFixed(1)} s` : "--";
    if (kpiAvgWait) kpiAvgWait.textContent = m.avg_wait_sec !== undefined ? `${m.avg_wait_sec.toFixed(2)} s` : "--";
    if (kpiRuntime) kpiRuntime.textContent = data.runtime_ms !== undefined ? `${data.runtime_ms.toFixed(1)} ms` : "--";

    // Delay Reduction vs Baseline
    if (kpiDelayReduction) {
      if (data.baseline_comparison && data.baseline_comparison.delay_reduction_pct !== undefined) {
        const red = data.baseline_comparison.delay_reduction_pct;
        kpiDelayReduction.textContent = `${red >= 0 ? "+" : ""}${red.toFixed(1)}%`;
        if (kpiDelayReductionCaption) kpiDelayReductionCaption.textContent = "Improvement vs Fixed-Time";
      } else if (algoName === "fixed-time") {
        kpiDelayReduction.textContent = "+0.0%";
        if (kpiDelayReductionCaption) kpiDelayReductionCaption.textContent = "Baseline reference";
      } else {
        kpiDelayReduction.textContent = "--";
      }
    }

    // Timing Plan on Intersection Cards
    if (data.timing_plan) {
      renderTimingPlan(data.timing_plan);
    }
  }

  function renderTimingPlan(timingPlan) {
    intersections.forEach((iid) => {
      const timing = timingPlan[iid] || timingPlan[`(${iid})`];
      if (!timing) return;

      const nsG = timing.ns_green;
      const ewG = timing.ew_green;
      const cycle = nsG + ewG || 60;

      const nsPct = Math.round((nsG / cycle) * 100);
      const ewPct = 100 - nsPct;

      const badge = document.getElementById(`badge-timing-${iid}`);
      const labelNS = document.getElementById(`label-ns-${iid}`);
      const labelEW = document.getElementById(`label-ew-${iid}`);
      const barNS = document.getElementById(`bar-ns-${iid}`);
      const barEW = document.getElementById(`bar-ew-${iid}`);

      if (badge) badge.textContent = `${nsG}s / ${ewG}s`;
      if (labelNS) labelNS.textContent = `NS: ${nsG}s (${nsPct}%)`;
      if (labelEW) labelEW.textContent = `EW: ${ewG}s (${ewPct}%)`;
      if (barNS) barNS.style.width = `${nsPct}%`;
      if (barEW) barEW.style.width = `${ewPct}%`;
    });
  }

  // -------------------------------------------------------------------------
  // Optimization History Log (GET /api/results)
  // -------------------------------------------------------------------------
  async function loadResultsHistory() {
    try {
      const res = await fetch("/api/results?limit=15");
      const data = await res.json();

      if (!res.ok || data.status !== "ok") {
        return;
      }

      renderHistoryTable(data.results || []);
    } catch (err) {
      console.warn("Could not load history log:", err);
    }
  }

  function renderHistoryTable(results) {
    if (!tableResultsBody) return;

    if (!results || results.length === 0) {
      tableResultsBody.innerHTML = `
        <tr>
          <td colspan="10" class="text-center text-muted">No runs recorded yet. Execute an optimizer above to populate.</td>
        </tr>
      `;
      return;
    }

    tableResultsBody.innerHTML = results
      .map((item) => {
        const m = item.metrics || {};
        const runId = item.run_id || "--";
        const algo = formatAlgorithmName(item.algorithm || "--");
        const status = item.status || "ok";
        const totalVeh = m.total_vehicles ?? "--";
        const served = m.vehicles_served ?? "--";
        const queue = m.remaining_queue ?? "--";
        const wait = m.avg_wait_sec !== undefined ? `${m.avg_wait_sec.toFixed(2)}` : "--";
        const delay = m.total_delay_sec !== undefined ? `${m.total_delay_sec.toFixed(1)}` : "--";
        const runtime = item.runtime_ms !== undefined ? `${item.runtime_ms.toFixed(1)} ms` : "--";

        let redText = "--";
        if (item.baseline_comparison && item.baseline_comparison.delay_reduction_pct !== undefined) {
          const r = item.baseline_comparison.delay_reduction_pct;
          redText = `${r >= 0 ? "+" : ""}${r.toFixed(1)}%`;
        } else if (item.algorithm === "fixed-time") {
          redText = "+0.0%";
        }

        return `
          <tr>
            <td><code>${runId}</code></td>
            <td><strong>${algo}</strong></td>
            <td><span class="status-badge status-${status}">${status}</span></td>
            <td>${totalVeh}</td>
            <td class="kpi-served">${served}</td>
            <td class="kpi-queue">${queue}</td>
            <td>${wait}</td>
            <td>${delay}</td>
            <td class="kpi-delta">${redText}</td>
            <td>${runtime}</td>
          </tr>
        `;
      })
      .join("");
  }

  function formatAlgorithmName(raw) {
    if (raw === "fixed-time") return "Fixed-Time (Baseline)";
    if (raw === "traffic-responsive") return "Traffic-Responsive";
    if (raw === "qaoa") return "QAOA Quantum";
    if (raw === "greedy") return "Classical Greedy";
    return raw;
  }

  // -------------------------------------------------------------------------
  // Event Listeners Binding
  // -------------------------------------------------------------------------
  // Apply traffic
  if (btnApplyTraffic) {
    btnApplyTraffic.addEventListener("click", applyCustomTraffic);
  }

  // Refresh traffic
  if (btnRefreshTraffic) {
    btnRefreshTraffic.addEventListener("click", loadTrafficState);
  }

  // Scenario buttons
  scenarioButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const scenario = btn.dataset.scenario;
      if (scenario) loadScenario(scenario, btn);
    });
  });

  // Fixed-Time Baseline
  if (btnOptBaseline) {
    btnOptBaseline.addEventListener("click", () => {
      runOptimization("/api/optimize/baseline", btnOptBaseline, {});
    });
  }

  // Traffic-Responsive
  if (btnOptResponsive) {
    btnOptResponsive.addEventListener("click", () => {
      runOptimization("/api/optimize/responsive", btnOptResponsive, {});
    });
  }

  // QAOA Quantum
  if (btnOptQAOA) {
    btnOptQAOA.addEventListener("click", () => {
      const pVal = parseInt(selectQAOAP?.value || "1", 10);
      const shotsVal = parseInt(selectQAOAShots?.value || "1024", 10);
      const maxiterVal = parseInt(inputQAOAMaxiter?.value || "50", 10);
      const seedVal = parseInt(inputQAOASeed?.value || "42", 10);

      const payload = {
        p_layers: isNaN(pVal) ? 1 : pVal,
        shots: isNaN(shotsVal) ? 1024 : shotsVal,
        maxiter: isNaN(maxiterVal) ? 50 : maxiterVal,
        seed: isNaN(seedVal) ? 42 : seedVal,
        timeout_sec: 30.0,
      };

      runOptimization("/api/optimize/qaoa", btnOptQAOA, payload);
    });
  }

  // Refresh history
  if (btnRefreshHistory) {
    btnRefreshHistory.addEventListener("click", loadResultsHistory);
  }

  // -------------------------------------------------------------------------
  // Initial Bootstrapping
  // -------------------------------------------------------------------------
  loadTrafficState();
  loadResultsHistory();
});

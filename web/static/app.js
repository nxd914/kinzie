const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderMetrics(metrics) {
  const container = document.getElementById("metrics");
  container.innerHTML = "";
  const cards = [
    ["Total Transactions", metrics.total_transactions],
    ["Flagged Transactions", metrics.flagged_transactions],
    ["Total Volume", currency.format(metrics.total_volume)],
    ["At-Risk Volume", currency.format(metrics.at_risk_volume)],
  ];
  cards.forEach(([title, value]) => {
    const card = el("article", "metric");
    card.append(el("div", "metric-title", title));
    card.append(el("div", "metric-value", String(value)));
    container.append(card);
  });
}

function renderProcessorSummary(rows) {
  const container = document.getElementById("processor-summary");
  container.innerHTML = "";
  const list = el("div", "summary-list");
  rows.forEach((row) => {
    const item = el("div", "summary-item");
    const left = el("div");
    left.append(el("div", "", row.processor));
    left.append(
      el(
        "div",
        "summary-meta",
        `${row.transactions} transactions • ${row.flagged} flagged`
      )
    );
    const right = el("div", "", currency.format(row.total_amount));
    item.append(left, right);
    list.append(item);
  });
  container.append(list);
}

function renderDiscrepancySummary(rows) {
  const container = document.getElementById("discrepancy-summary");
  container.innerHTML = "";
  const list = el("div", "discrepancy-list");
  rows.forEach((row) => {
    const item = el("div", "discrepancy-item");
    const left = el("div");
    left.append(el("div", "", row.discrepancy_type));
    left.append(
      el("div", "discrepancy-meta", `${row.count} transactions flagged`)
    );
    const right = el("div", "", currency.format(row.total_amount));
    item.append(left, right);
    list.append(item);
  });
  container.append(list);
}

function renderActionQueue(rows) {
  const container = document.getElementById("action-queue");
  container.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    [
      row.transaction_at,
      row.processor,
      row.reference_id,
      row.terminal_id,
      row.transaction_type,
      currency.format(row.amount),
    ].forEach((value) => {
      tr.append(el("td", "", String(value)));
    });
    const flag = el("td");
    flag.append(el("span", "badge", row.discrepancy_type));
    tr.append(flag);
    tr.append(el("td", "", row.recommended_action));
    container.append(tr);
  });
}

async function loadDashboard() {
  const response = await fetch("/api/reconciliation");
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  const payload = await response.json();
  renderMetrics(payload.metrics);
  renderProcessorSummary(payload.processor_summary);
  renderDiscrepancySummary(payload.discrepancy_summary);
  renderActionQueue(payload.discrepancies);
  document.getElementById("generated-at").textContent = `Generated ${new Date(
    payload.generated_at
  ).toLocaleString()}`;
}

loadDashboard().catch((error) => {
  document.getElementById("metrics").textContent = error.message;
});

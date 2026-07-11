let equityChart = null;
let latestCycles = [];
let showOnlyTrades = false;

// value === null/undefined means "not enough data yet" - shown as a dash,
// never silently coerced to 0. A real $0.00 and "no data" are different
// things and should never look the same on screen.
const money = (value) => {
    if (value === null || value === undefined) return "—";
    const num = Number(value);
    const sign = num < 0 ? "-" : "";
    return sign + "$" + Math.abs(num).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
};

const percent = (value) => {
    if (value === null || value === undefined) return "—";
    return Number(value).toFixed(2) + "%";
};

const number = (value, decimals = 2) => {
    if (value === null || value === undefined) return "—";
    return Number(value).toFixed(decimals);
};

async function loadDashboard() {

    try {

        const response = await fetch("data.json?t=" + Date.now());

        if (!response.ok) {
            throw new Error("Unable to load dashboard data.");
        }

        const data = await response.json();

        document.getElementById("mode-text").textContent =
            (data.mode || "paper").toUpperCase();

        document.getElementById("bot-text").textContent =
            data.halted ? "HALTED" : "RUNNING";

        const hour = new Date().getHours();

        document.getElementById("market-text").textContent =
            (hour >= 9 && hour < 16) ? "Open" : "Closed";

        const haltBanner = document.getElementById("halt-banner");

        if (data.halted) {

            haltBanner.classList.remove("hidden");

            let reason = "Unknown";

            if (data.recent_halts?.length) {
                reason = data.recent_halts[0].reason;
            }

            haltBanner.textContent =
                "Trading Halted - " + reason;

        } else {

            haltBanner.classList.add("hidden");

        }

        // --------------------
        // Plain English Summary
        // --------------------

        const summaryList = document.getElementById("plain-summary");
        summaryList.innerHTML = "";

        if (data.plain_summary?.length) {
            data.plain_summary.forEach(line => {
                const li = document.createElement("li");
                li.textContent = line;
                summaryList.appendChild(li);
            });
        } else {
            summaryList.innerHTML = "<li>Nothing to report yet.</li>";
        }

        // --------------------
        // Top cards
        // --------------------

        document.getElementById("portfolio-value").textContent =
            money(data.portfolio_value);

        const dailyPlEl = document.getElementById("daily-pl");
        dailyPlEl.textContent = money(data.daily_pl);
        dailyPlEl.classList.remove("profit", "loss");
        if (data.daily_pl !== null && data.daily_pl !== undefined) {
            dailyPlEl.classList.add(data.daily_pl >= 0 ? "profit" : "loss");
        }

        document.getElementById("cash").textContent =
            money(data.cash);

        document.getElementById("buying-power").textContent =
            money(data.buying_power);

        const returnEl = document.getElementById("return");
        returnEl.textContent = percent(data.total_pnl_pct);
        returnEl.classList.remove("profit", "loss");
        if (data.total_pnl_pct !== null && data.total_pnl_pct !== undefined) {
            returnEl.classList.add(data.total_pnl_pct >= 0 ? "profit" : "loss");
        }

        document.getElementById("positions").textContent =
            data.open_positions ?? 0;

        // --------------------
        // AI Decision
        // --------------------

        const decision = data.current_decision || {};

        document.getElementById("decision-ticker").textContent =
            decision.ticker || "---";

        document.getElementById("decision-action").textContent =
            (decision.action || "WAIT").toUpperCase();

        document.getElementById("decision-confidence").textContent =
            decision.composite_score !== undefined
                ? percent(Math.abs(decision.composite_score) * 100)
                : "—";

        document.getElementById("decision-score").textContent =
            decision.composite_score !== undefined
                ? number(decision.composite_score, 3)
                : "—";

        document.getElementById("technical-reason").textContent =
            "Technical Score: " +
            (decision.technical_score !== undefined
                ? percent(decision.technical_score * 100)
                : "—");

        document.getElementById("fundamental-reason").textContent =
            "Fundamental Score: " +
            (decision.fundamental_score !== undefined
                ? percent(decision.fundamental_score * 100)
                : "—");

        document.getElementById("news-reason").textContent =
            "News Score: " +
            (decision.news_score !== undefined && decision.news_score !== null
                ? percent(decision.news_score * 100)
                : "—");

        document.getElementById("risk-reason").textContent =
            (decision.risk_decision || "Unknown").toUpperCase() +
            " - " +
            (decision.risk_reason || "");

        // --------------------
        // Open Positions
        // --------------------

        const positionsTable = document.getElementById("positions-table");
        positionsTable.innerHTML = "";

        if (data.positions?.length) {

            data.positions.forEach(pos => {

                const row = document.createElement("tr");
                const pl = Number(pos.unrealized_pl || 0);

                row.innerHTML = `
                    <td>${pos.ticker}</td>
                    <td>${number(pos.qty, 0)}</td>
                    <td>${money(pos.avg_entry_price)}</td>
                    <td>${money(pos.current_price)}</td>
                    <td>${money(pos.market_value)}</td>
                    <td class="${pl >= 0 ? "profit" : "loss"}">
                        ${money(pos.unrealized_pl)} (${percent(pos.unrealized_plpc)})
                    </td>
                `;

                positionsTable.appendChild(row);

            });

        } else {

            positionsTable.innerHTML =
                "<tr><td colspan='6'>No open positions.</td></tr>";

        }

        // --------------------
        // Sector Allocation
        // --------------------

        const sectorEl = document.getElementById("sector-allocation");
        sectorEl.innerHTML = "";

        if (data.sector_allocation?.length) {

            data.sector_allocation.forEach(s => {

                const row = document.createElement("div");
                row.className = "confidence-bar-row";
                row.innerHTML = `
                    <div class="confidence-bar-label">${s.sector}</div>
                    <div class="confidence-bar-track">
                        <div class="confidence-bar-fill" style="width:${s.pct}%"></div>
                    </div>
                    <div class="confidence-bar-count">${s.pct}%</div>
                `;
                sectorEl.appendChild(row);

            });

        } else {

            sectorEl.innerHTML =
                "<div class='metric-row'><span>No open positions to break down yet.</span></div>";

        }

        // --------------------
        // Performance
        // --------------------

        const stats = data.trade_stats || {};

        document.getElementById("win-rate").textContent =
            percent(stats.win_rate);

        document.getElementById("profit-factor").textContent =
            number(stats.profit_factor);

        document.getElementById("sharpe").textContent =
            number(stats.sharpe_ratio);

        document.getElementById("drawdown").textContent =
            percent(stats.max_drawdown_pct);

        document.getElementById("expectancy").textContent =
            money(stats.expectancy);

        document.getElementById("total-trades").textContent =
            stats.total_trades ?? 0;

        document.getElementById("avg-win").textContent =
            money(stats.average_win);

        document.getElementById("avg-loss").textContent =
            stats.average_loss !== null && stats.average_loss !== undefined
                ? "-" + money(stats.average_loss)
                : "—";

        document.getElementById("avg-hold").textContent =
            stats.avg_hold_hours !== null && stats.avg_hold_hours !== undefined
                ? number(stats.avg_hold_hours, 1) + " hrs"
                : "—";

        document.getElementById("largest-win").textContent =
            money(stats.largest_win);

        document.getElementById("largest-loss").textContent =
            money(stats.largest_loss);

        // --------------------
        // Market Context
        // --------------------

        const context = data.market_context || {};

        const trendEl = document.getElementById("spy-trend");
        trendEl.textContent = context.trend
            ? context.trend.charAt(0).toUpperCase() + context.trend.slice(1)
            : "—";
        trendEl.classList.remove("profit", "loss");
        if (context.trend === "bullish") trendEl.classList.add("profit");
        if (context.trend === "bearish") trendEl.classList.add("loss");

        const contextReturnEl = document.getElementById("context-return");
        contextReturnEl.textContent = percent(data.total_pnl_pct);
        contextReturnEl.classList.remove("profit", "loss");
        if (data.total_pnl_pct !== null && data.total_pnl_pct !== undefined) {
            contextReturnEl.classList.add(data.total_pnl_pct >= 0 ? "profit" : "loss");
        }

        const spyReturnEl = document.getElementById("spy-return");
        spyReturnEl.textContent = percent(context.spy_return_pct);
        spyReturnEl.classList.remove("profit", "loss");
        if (context.spy_return_pct !== null && context.spy_return_pct !== undefined) {
            spyReturnEl.classList.add(context.spy_return_pct >= 0 ? "profit" : "loss");
        }

        document.getElementById("cash-deployed").textContent =
            percent(data.cash_deployed_pct);

        document.getElementById("risk-reward").textContent =
            data.risk_reward_ratio
                ? `1 : ${data.risk_reward_ratio}`
                : "—";

        // --------------------
        // Live Watchlist
        // --------------------

        const watchlistTable = document.getElementById("watchlist-table");
        watchlistTable.innerHTML = "";

        if (data.watchlist_snapshot?.length) {

            data.watchlist_snapshot.forEach(row => {

                const tr = document.createElement("tr");
                const action = (row.action || "none").toLowerCase();

                tr.innerHTML = `
                    <td>${row.ticker}</td>
                    <td>${row.technical_score !== null ? number(row.technical_score, 2) : "—"}</td>
                    <td>${row.fundamental_score !== null ? number(row.fundamental_score, 2) : "—"}</td>
                    <td>${row.news_score !== null && row.news_score !== undefined ? number(row.news_score, 2) : "—"}</td>
                    <td>${row.composite_score !== null ? number(row.composite_score, 3) : "—"}</td>
                    <td class="${action}">${action.toUpperCase()}</td>
                `;

                watchlistTable.appendChild(tr);

            });

        } else {

            watchlistTable.innerHTML =
                "<tr><td colspan='6'>No watchlist data yet.</td></tr>";

        }

        // --------------------
        // Decision Quality
        // --------------------

        const rejectionsEl = document.getElementById("rejection-reasons");
        rejectionsEl.innerHTML = "";

        if (data.rejection_reasons?.length) {
            data.rejection_reasons.forEach(r => {
                const row = document.createElement("div");
                row.className = "metric-row";
                row.innerHTML = `<span>${r.reason || "Unknown"}</span><span>${r.count}</span>`;
                rejectionsEl.appendChild(row);
            });
        } else {
            rejectionsEl.innerHTML =
                "<div class='metric-row'><span>No rejected trades yet.</span></div>";
        }

        const dist = data.confidence_distribution || { low: 0, medium: 0, high: 0 };
        const distTotal = (dist.low || 0) + (dist.medium || 0) + (dist.high || 0);

        const distEl = document.getElementById("confidence-distribution");
        distEl.innerHTML = "";

        if (distTotal > 0) {

            [
                ["Low (0.40–0.55)", dist.low],
                ["Medium (0.55–0.70)", dist.medium],
                ["High (0.70+)", dist.high],
            ].forEach(([label, count]) => {

                const pct = distTotal ? (count / distTotal) * 100 : 0;

                const row = document.createElement("div");
                row.className = "confidence-bar-row";
                row.innerHTML = `
                    <div class="confidence-bar-label">${label}</div>
                    <div class="confidence-bar-track">
                        <div class="confidence-bar-fill" style="width:${pct}%"></div>
                    </div>
                    <div class="confidence-bar-count">${count}</div>
                `;
                distEl.appendChild(row);

            });

        } else {

            distEl.innerHTML =
                "<div class='metric-row'><span>No proposals scored yet.</span></div>";

        }

        // --------------------
        // Recent Decisions
        // --------------------

        latestCycles = data.recent_cycles || [];
        renderDecisionsTable();

        // --------------------
        // Completed Trades
        // --------------------

        const tradesTable = document.getElementById("trades-table");

        if (tradesTable) {

            tradesTable.innerHTML = "";

            if (data.recent_trades?.length) {

                data.recent_trades.forEach(trade => {

                    const row = document.createElement("tr");

                    const pnl = Number(trade.pnl || 0);

                    row.innerHTML = `
                        <td>${trade.ticker}</td>
                        <td class="${pnl >= 0 ? "profit" : "loss"}">${money(pnl)}</td>
                        <td class="${pnl >= 0 ? "profit" : "loss"}">${percent(trade.pnl_pct)}</td>
                        <td>${trade.quantity}</td>
                        <td>${number(trade.hold_time_hours, 1)}</td>
                    `;

                    tradesTable.appendChild(row);

                });

            } else {

                tradesTable.innerHTML =
                    "<tr><td colspan='5'>No completed trades yet.</td></tr>";

            }

        }

        // --------------------
        // Equity Chart
        // --------------------

        const history = data.equity_history || [];

        if (history.length) {

            const labels = history.map(p =>
                new Date(p.timestamp).toLocaleString(undefined, {
                    month: "short",
                    day: "numeric",
                    hour: "numeric",
                    minute: "2-digit"
                })
            );

            const values = history.map(p =>
                Number(p.equity)
            );

            if (equityChart) {
                equityChart.destroy();
            }

            equityChart = new Chart(
                document.getElementById("equityChart"),
                {
                    type: "line",
                    data: {
                        labels,
                        datasets: [{
                            label: "Portfolio Value",
                            data: values,
                            borderWidth: 2,
                            borderColor: "#3B82F6",
                            backgroundColor: "rgba(59,130,246,.15)",
                            fill: true,
                            pointRadius: 2,
                            pointHoverRadius: 5,
                            tension: .25
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: {
                            mode: "index",
                            intersect: false
                        },
                        scales: {
                            x: {
                                ticks: {
                                    // Full history can be hundreds of points -
                                    // let Chart.js thin the labels instead of
                                    // cramming every timestamp onto the axis.
                                    autoSkip: true,
                                    maxRotation: 45,
                                    minRotation: 0
                                }
                            }
                        },
                        plugins: {
                            legend: {
                                display: false
                            },
                            tooltip: {
                                callbacks: {
                                    title: (items) => {
                                        const point = history[items[0].dataIndex];
                                        return new Date(point.timestamp).toLocaleString();
                                    },
                                    label: (item) => money(item.parsed.y)
                                }
                            }
                        }
                    }
                }
            );

        }

    } catch (error) {

        console.error(error);

        document.getElementById("decision-table").innerHTML =
            "<tr><td colspan='6'>Unable to load dashboard.</td></tr>";

    }

}

function renderDecisionsTable() {

    const tbody = document.getElementById("decision-table");
    tbody.innerHTML = "";

    const rows = showOnlyTrades
        ? latestCycles.filter(c => (c.action || "none") !== "none")
        : latestCycles;

    if (rows.length) {

        rows.forEach(cycle => {

            const row = document.createElement("tr");
            const action = (cycle.action || "none").toLowerCase();

            row.innerHTML = `
                <td>${new Date(cycle.timestamp).toLocaleString()}</td>
                <td>${cycle.ticker || "-"}</td>
                <td>${cycle.composite_score !== null && cycle.composite_score !== undefined ? number(cycle.composite_score, 3) : "—"}</td>
                <td class="${action}">${action.toUpperCase()}</td>
                <td class="${cycle.risk_decision === "approved" ? "approved" : "rejected"}">${cycle.risk_decision || "-"}</td>
                <td>${cycle.risk_reason || "-"}</td>
            `;

            tbody.appendChild(row);

        });

    } else {

        tbody.innerHTML = showOnlyTrades
            ? "<tr><td colspan='6'>No trades in the recent history yet.</td></tr>"
            : "<tr><td colspan='6'>No decisions yet.</td></tr>";

    }

}

document.getElementById("hide-none-toggle").addEventListener("change", (e) => {
    showOnlyTrades = e.target.checked;
    renderDecisionsTable();
});

loadDashboard();

setInterval(loadDashboard, 30000);

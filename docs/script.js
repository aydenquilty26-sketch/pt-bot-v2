let equityChart = null;

const money = (value) => {
    const num = Number(value || 0);
    return "$" + num.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
};

const percent = (value) => {
    return Number(value || 0).toFixed(2) + "%";
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

        document.getElementById("portfolio-value").textContent =
            money(data.portfolio_value);

        document.getElementById("daily-pl").textContent =
            money(data.daily_pl);

        document.getElementById("cash").textContent =
            money(data.cash);

        document.getElementById("buying-power").textContent =
            money(data.buying_power);

        document.getElementById("return").textContent =
            percent(data.total_pnl_pct);

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
            percent((decision.composite_score || 0) * 100);

        document.getElementById("decision-score").textContent =
            Number(decision.composite_score || 0).toFixed(3);

        document.getElementById("technical-reason").textContent =
            "Technical Score: " +
            percent((decision.technical_score || 0) * 100);

        document.getElementById("fundamental-reason").textContent =
            "Fundamental Score: " +
            percent((decision.fundamental_score || 0) * 100);

        document.getElementById("risk-reason").textContent =
            (decision.risk_decision || "Unknown").toUpperCase() +
            " - " +
            (decision.risk_reason || "");

        // --------------------
        // Performance
        // --------------------

        const stats = data.trade_stats || {};

        document.getElementById("win-rate").textContent =
            percent(stats.win_rate || 0);

        document.getElementById("profit-factor").textContent =
            stats.total_trades ?? 0;

        document.getElementById("sharpe").textContent =
            stats.wins ?? 0;

        document.getElementById("drawdown").textContent =
            stats.losses ?? 0;

        document.getElementById("expectancy").textContent =
            money(stats.average_trade || 0);

        // --------------------
        // Recent Decisions
        // --------------------

        const tbody = document.getElementById("decision-table");
        tbody.innerHTML = "";

        if (data.recent_cycles?.length) {

            data.recent_cycles.forEach(cycle => {

                const row = document.createElement("tr");

                row.innerHTML = `
                    <td>${new Date(cycle.timestamp).toLocaleString()}</td>
                    <td>${cycle.ticker || "-"}</td>
                    <td>${Number(cycle.composite_score || 0).toFixed(3)}</td>
                    <td class="${(cycle.action || "").toLowerCase()}">${(cycle.action || "").toUpperCase()}</td>
                    <td class="${cycle.risk_decision === "approved" ? "approved" : "rejected"}">${cycle.risk_decision || "-"}</td>
                    <td>${cycle.risk_reason || "-"}</td>
                `;

                tbody.appendChild(row);

            });

        } else {

            tbody.innerHTML =
                "<tr><td colspan='6'>No decisions yet.</td></tr>";

        }

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
                        <td>${Number(trade.hold_time_hours || 0).toFixed(1)}</td>
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
                new Date(p.timestamp).toLocaleDateString()
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
                            tension: .25
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                display: false
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

loadDashboard();

setInterval(loadDashboard, 30000);

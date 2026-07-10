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

        // -----------------------
        // STATUS
        // -----------------------

        document.getElementById("mode-text").textContent =
            (data.mode || "paper").toUpperCase();

        document.getElementById("bot-text").textContent =
            data.halted ? "HALTED" : "RUNNING";

        const hour = new Date().getHours();

        document.getElementById("market-text").textContent =
            (hour >= 9 && hour < 16) ? "Open" : "Closed";

        // -----------------------
        // HALT BANNER
        // -----------------------

        const haltBanner = document.getElementById("halt-banner");

        if (data.halted) {

            haltBanner.classList.remove("hidden");

            let reason = "Unknown";

            if (data.recent_halts &&
                data.recent_halts.length > 0) {

                reason = data.recent_halts[0].reason;
            }

            haltBanner.textContent =
                "Trading Halted - " + reason;

        } else {

            haltBanner.classList.add("hidden");

        }

        // -----------------------
        // TOP STATS
        // -----------------------

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

        // -----------------------
        // AI DECISION
        // -----------------------

        const decision = data.current_decision || {};

        document.getElementById("decision-ticker").textContent =
            decision.ticker || "---";

        document.getElementById("decision-action").textContent =
            (decision.action || "WAIT").toUpperCase();

        document.getElementById("decision-confidence").textContent =
            percent((decision.composite_score || 0) * 100);

        document.getElementById("decision-score").textContent =
            Number(decision.composite_score || 0).toFixed(3);

        // -----------------------
        // AI REASONING
        // -----------------------

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
        // -----------------------
        // RECENT DECISIONS TABLE
        // -----------------------

        const tbody = document.getElementById("decision-table");
        tbody.innerHTML = "";

        if (data.recent_cycles && data.recent_cycles.length > 0) {

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

        // -----------------------
        // EQUITY CHART
        // -----------------------

        const history = data.equity_history || [];

        if (history.length > 0) {

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
                        labels: labels,
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
                        },
                        scales: {
                            x: {
                                ticks: {
                                    color: "#8D98A5"
                                },
                                grid: {
                                    color: "rgba(255,255,255,.05)"
                                }
                            },
                            y: {
                                ticks: {
                                    color: "#8D98A5"
                                },
                                grid: {
                                    color: "rgba(255,255,255,.05)"
                                }
                            }
                        }
                    }
                }
            );

        }

    }

    catch (error) {

        console.error(error);

        document.getElementById("decision-table").innerHTML =
            "<tr><td colspan='6'>Unable to load dashboard.</td></tr>";

    }

}

loadDashboard();

setInterval(loadDashboard, 30000);

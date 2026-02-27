async function loadGraph() {

    const response = await fetch("/api/graph");
    const data = await response.json();

    const ctx = document.getElementById("killsChart");

    new Chart(ctx, {
        type: "bar",
        data: {
            labels: data.players,
            datasets: [{
                label: "Total Kills",
                data: data.kills,
                borderWidth: 1
            }]
        }
    });
}

loadGraph();
async function loadReport(start, end){
    let url = "/api/report";
    const params = [];
    if(start) params.push(`start=${start}`);
    if(end) params.push(`end=${end}`);
    if(params.length) url += '?' + params.join('&');
    const res = await fetch(url);
    const data = await res.json();

    let names=[];
    let kills=[];
    let winrate=[];

    let bestPlayer="";
    let bestKills=0;

    data.forEach(p=>{
        names.push(p.name);
        kills.push(p.kills);
        winrate.push(p.winrate);

        if(p.kills>bestKills){
            bestKills=p.kills;
            bestPlayer=p.name;
        }
    });

    // Kills Chart
    new Chart(document.getElementById("killsChart"),{
        type:"bar",
        data:{
            labels:names,
            datasets:[{
                label:"Total Kills",
                data:kills
            }]
        }
    });

    // Winrate Chart
    new Chart(document.getElementById("winChart"),{
        type:"pie",
        data:{
            labels:names,
            datasets:[{
                label:"Win Rate",
                data:winrate
            }]
        }
    });

    // Text Report
    document.getElementById("report").innerHTML=
        "<h3>🔥 Best Performer: "+bestPlayer+"</h3>";
}

// initial load
loadReport();

// wire up filter controls if present
const startInput = document.getElementById('filterStart');
const endInput = document.getElementById('filterEnd');
const applyBtn = document.getElementById('applyFilter');
if(applyBtn){
    applyBtn.addEventListener('click', ()=>{
        const s = startInput.value;
        const e = endInput.value;
        loadReport(s,e);
    });
}
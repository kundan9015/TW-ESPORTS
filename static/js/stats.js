// Load history table
async function loadHistory(){
    const res = await fetch("/api/my_stats");
    const data = await res.json();

    let table = document.querySelector("#historyTable tbody");
    table.innerHTML = "";

    data.forEach(r=>{
        table.innerHTML += `
        <tr>
            <td>${r.date}</td>
            <td>${r.kills}</td>
            <td>${r.booyah}</td>
            <td>${r.damage}</td>
            <td>${r.survival}</td>
        </tr>`;
    });
}

// AJAX form submit
document.addEventListener("DOMContentLoaded", ()=>{
    loadHistory();

    document.getElementById("statsForm").addEventListener("submit", async function(e){
        e.preventDefault();

        let formData = new FormData(this);

        await fetch("/add_stats",{
            method:"POST",
            body:formData
        });

        this.reset();
        loadHistory();
        alert("Record Uploaded!");
    });
});
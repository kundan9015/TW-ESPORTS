// Auto refresh leaderboard every 10 seconds
setInterval(() => {
    fetch("/leaderboard")
    .then(res => res.text())
    .then(html => {
        let parser = new DOMParser();
        let doc = parser.parseFromString(html, "text/html");

        let newTable = doc.querySelector("#board tbody");
        document.querySelector("#board tbody").innerHTML = newTable.innerHTML;
    });
}, 10000);
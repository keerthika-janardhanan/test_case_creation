let recording = false;

document.getElementById("start").addEventListener("click", () => {
    recording = true;
    alert("Recording started!");
});

document.getElementById("stop").addEventListener("click", () => {
    if (!recording) return;
    recording = false;

    const flowName = document.getElementById("flowName").value;
    const userId = document.getElementById("userId").value;

    chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
        chrome.scripting.executeScript({
            target: {tabId: tabs[0].id},
            function: sendRecordedFlow,
            args: [flowName, userId]
        });
    });
});

function sendRecordedFlow(flowName, userId) {
    fetch("http://localhost:8503/ingest_flow", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            flow_name: flowName,
            user: userId,
            steps: window.steps || []
        })
    })
    .then(() => alert("Flow sent to backend!"))
    .catch(e => alert("Failed to send flow: " + e));
}

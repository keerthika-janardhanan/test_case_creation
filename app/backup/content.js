window.steps = window.steps || [];

function sanitizeInput(value) {
    return "{{test_data}}";
}

function getSelector(el) {
    if (!el) return null;
    let path = [];
    while (el && el.nodeType === Node.ELEMENT_NODE) {
        let selector = el.nodeName.toLowerCase();
        if (el.id) {
            selector += `#${el.id}`;
            path.unshift(selector);
            break;
        } else {
            let sib = el, nth = 1;
            while (sib = sib.previousElementSibling) nth++;
            selector += `:nth-child(${nth})`;
        }
        path.unshift(selector);
        el = el.parentNode;
    }
    return path.join(" > ");
}

function recordEvent(event) {
    let step = {
        type: event.type,
        selector: getSelector(event.target),
        value: event.type === "input" ? sanitizeInput(event.target.value) : null,
        tag: event.target.tagName,
        timestamp: new Date().toISOString()
    };
    window.steps.push(step);
}

document.addEventListener("click", recordEvent, true);
document.addEventListener("input", recordEvent, true);

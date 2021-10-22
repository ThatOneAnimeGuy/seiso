(function() {
    var logs = [];
    var import_id = page_data.import_id;
    var run_fetch = true;

    window.addEventListener('load', async function() {
        await fetchAndShowLogs();
    });

    async function fetchAndShowLogs() {
        [run_fetch, logs] = await fetchNewLogs(import_id, logs);
        var logContainer = document.getElementById('logs');
        var lastChild = logContainer.lastChild;
        var shouldScrollToBottom = true;
        if (lastChild) {
            shouldScrollToBottom = isScrolledIntoView(logContainer.lastChild);
        }

        var currentChildCount = logContainer.childElementCount;
        var newLastChild;
        logs.forEach((msg, idx) => {
            if (idx < currentChildCount) { return; }

            var node = document.createElement('p');
            node.appendChild(document.createTextNode(msg));
            logContainer.appendChild(node);
            newLastChild = node;
        });

        if (newLastChild && shouldScrollToBottom) {
            newLastChild.scrollIntoView();
        }

        if (run_fetch) {
            setTimeout(async () => {
                await fetchAndShowLogs();
            }, 5000);
        }
    }
})();

async function fetchNewLogs(import_id, logs) {
    return await fetch(`/api/logs/${import_id}`)
    .then(resp => {
        var cont = true;
        if (resp.status === 207) {
            cont = false;
        }
        return resp.json().then(data => {
            return [cont, data];
        });
    })
    .catch(() => {
        logs.push(`Error fetching logs. We'll keep trying. Your log id is ${import_id}.`);
        return [true, logs];
    });
}

function isScrolledIntoView(el) {
    var parent = document.getElementsByClassName('info')[0];
    var height = parent.scrollTop;
    return el.offsetTop >= height && (el.offsetTop <= height + parent.offsetHeight + 10 + el.offsetHeight)
}

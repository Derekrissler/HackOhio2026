// Service worker: relays requests from the content script to the local backend.
// (Content scripts on an https Canvas page can't reliably call http://localhost directly,
// but the extension's service worker can, thanks to host_permissions.)

const DEFAULT_BACKEND = "http://localhost:8000";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type !== "analyze") return;

  (async () => {
    try {
      const { backendUrl } = await chrome.storage.sync.get({ backendUrl: DEFAULT_BACKEND });
      const res = await fetch(`${backendUrl}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(msg.payload),
      });
      if (!res.ok) throw new Error(`Backend returned ${res.status}: ${await res.text()}`);
      sendResponse({ ok: true, data: await res.json() });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();

  return true; // keep the message channel open for the async response
});

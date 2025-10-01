// This script runs in the background and listens for the extension icon to be clicked.
chrome.action.onClicked.addListener((tab) => {
  // Check if the current tab is a Google Meet or Zoom meeting URL.
  if (
    tab.url && (tab.url.startsWith("https://meet.google.com/") || tab.url.includes(".zoom.us/wc/"))
  ) {
    // If it's a valid meeting page, inject the main content script.
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });
  } else {
    // If it's not a valid page, inform the user via the popup.
    chrome.scripting.executeScript({
        target: {tabId: tab.id},
        func: () => {
          alert("AI Proctor can only be activated on a Google Meet or Zoom page.");
        }
    });
  }
});

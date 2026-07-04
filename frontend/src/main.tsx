import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Analytics } from "@vercel/analytics/react";
import App from "./App";
import faviconUrl from "./assets/favicon.svg";
import "./index.css";

function ensureFavicon() {
  const existingLink = document.querySelector<HTMLLinkElement>("link[rel='icon']");
  const faviconLink = existingLink ?? document.createElement("link");
  faviconLink.rel = "icon";
  faviconLink.type = "image/svg+xml";
  faviconLink.href = faviconUrl;

  if (!existingLink) {
    document.head.appendChild(faviconLink);
  }
}

ensureFavicon();

// Vercel Analytics' script only exists when Vercel serves the app; mounting it
// on localhost/CI guarantees a 404 console error (caught by the e2e console-
// hygiene gate). Mount it only off-localhost.
const isLocalHost = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <App />
      {!isLocalHost && <Analytics />}
    </BrowserRouter>
  </React.StrictMode>
);

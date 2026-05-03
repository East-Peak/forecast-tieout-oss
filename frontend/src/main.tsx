import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
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

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <App />
    </BrowserRouter>
  </React.StrictMode>
);

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

/* Office.js is loaded via <script> in index.html.
   We wait for Office.onReady() before mounting React so that
   Office.context is available when components render. */

const mount = () => {
  ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
};

if (typeof Office !== "undefined") {
  Office.onReady(() => {
    console.log("[Agent Paperpal] Office.js ready — host:", Office.context.host);
    mount();
  });
} else {
  // Running outside of Word (e.g. plain browser for dev/testing)
  console.warn("[Agent Paperpal] Office.js not found — running in standalone mode");
  mount();
}

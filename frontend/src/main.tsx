import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

function App() {
  return (
    <main className="shell">
      <section className="status-panel">
        <p className="eyebrow">SENTINEL</p>
        <h1>Fraud detection dashboard scaffold</h1>
        <p>Infrastructure is ready for the demo dashboard sprint.</p>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

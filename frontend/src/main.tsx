import React from "react";
import { createRoot } from "react-dom/client";
import Landing from "./Landing";
import Dashboard from "./App";
import "./styles.css";

const page = window.location.pathname.startsWith("/demo") ? <Dashboard /> : <Landing />;

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{page}</React.StrictMode>,
);

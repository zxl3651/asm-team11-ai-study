import React from "react";
import { createRoot } from "react-dom/client";
import { ChatPanel } from "./components/ChatPanel";
import "./styles.css";

const root = createRoot(document.getElementById("root")!);
root.render(
  <React.StrictMode>
    <ChatPanel />
  </React.StrictMode>
);

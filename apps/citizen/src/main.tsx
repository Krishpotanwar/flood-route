import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@floodroute/ui/tokens.css";
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles/app.css";
import { App } from "./App";

const container = document.getElementById("root");

if (container) {
  const root = createRoot(container);
  root.render(
    <StrictMode>
      <App />
    </StrictMode>
  );
}

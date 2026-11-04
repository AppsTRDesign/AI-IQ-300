import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";
import { useStore } from "./lib/store";

// Automated layout checks (Playwright) switch views through the store; nothing in the app reads this.
window.__aiiq = useStore;

createRoot(document.getElementById("root")).render(<App />);

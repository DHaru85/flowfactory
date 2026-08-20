import { BrowserRouter } from "react-router-dom";
import { createRoot } from "react-dom/client";

import { App } from "@/App";
import "@/index.css";

const el = document.getElementById("root");
if (el === null) {
  throw new Error("缺少 #root");
}

createRoot(el).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>,
);

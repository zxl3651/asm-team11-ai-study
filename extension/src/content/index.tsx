import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { Widget } from "./Widget";

// 페이지 CSS 와 격리하기 위해 Shadow DOM 안에 위젯을 마운트한다.
const host = document.createElement("div");
host.id = "soma-mate-root";
document.body.appendChild(host);

const shadow = host.attachShadow({ mode: "open" });
const mount = document.createElement("div");
shadow.appendChild(mount);

createRoot(mount).render(
  <StrictMode>
    <Widget />
  </StrictMode>
);

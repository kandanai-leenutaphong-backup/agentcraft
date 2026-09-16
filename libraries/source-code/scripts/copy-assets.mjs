import { copyFileSync } from "node:fs";

copyFileSync(new URL("../frontend/source-code.css", import.meta.url), new URL("../dist/source-code.css", import.meta.url));
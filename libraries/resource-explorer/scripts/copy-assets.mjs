import { copyFileSync } from "node:fs";

for (const name of ["inventory.css", "explorer.css"]) {
  copyFileSync(new URL(`../frontend/${name}`, import.meta.url), new URL(`../dist/${name}`, import.meta.url));
}
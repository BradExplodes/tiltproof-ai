// The Electron main/preload are compiled to CommonJS, but desktop/package.json
// declares "type": "module" (for Vite). Node uses the nearest package.json, so
// we drop a CommonJS marker next to the compiled output. This makes Node treat
// dist-electron/*.js as CommonJS in both dev and the packaged app.asar.
import { mkdirSync, writeFileSync } from "node:fs";

mkdirSync("dist-electron", { recursive: true });
writeFileSync("dist-electron/package.json", JSON.stringify({ type: "commonjs" }, null, 2) + "\n");

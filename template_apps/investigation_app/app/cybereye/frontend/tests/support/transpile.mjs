// Load a real TypeScript module in `node --test`, without a bundler.
//
// The tests run the shipped modules rather than a copy, so this has to resolve the same import
// graph the bundler does: relative TypeScript files and installed @agentcraft exports.
// Other bare specifiers are left alone — Node
// resolves those itself. Everything else is compiled and inlined as a data URL, which is why
// no bundler or extra test dependency is needed to reach the shared event-stream decoder.
import { readFileSync, statSync } from "node:fs";
import ts from "typescript";

const compiled = new Map();

function resolveModule(specifier, parent) {
  const base = specifier.startsWith(".") ? new URL(specifier, parent) : null;
  if (!base) return null;
  for (const suffix of ["", ".ts", ".tsx", "/index.ts", "/index.tsx"]) {
    const candidate = new URL(base.href + suffix);
    if (statSync(candidate, { throwIfNoEntry: false })?.isFile()) return candidate;
  }
  throw new Error(`transpile: cannot resolve ${specifier} from ${parent.href}`);
}

function compileModule(url) {
  const cached = compiled.get(url.href);
  if (cached) return cached;
  const source = readFileSync(url, "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
  }).outputText.replace(/(\bfrom\s*)(["'])([^"']+)\2/g, (match, prefix, quote, specifier) => {
    if (specifier.startsWith("@agentcraft/")) return `${prefix}${quote}${import.meta.resolve(specifier)}${quote}`;
    const resolved = resolveModule(specifier, url);
    return resolved ? `${prefix}${quote}${compileModule(resolved)}${quote}` : match;
  });
  const dataUrl = `data:text/javascript;base64,${Buffer.from(output).toString("base64")}`;
  compiled.set(url.href, dataUrl);
  return dataUrl;
}

/** Import `filename`, resolved relative to `parent`, with its TypeScript dependencies inlined. */
export async function loadModule(filename, parent) {
  return import(compileModule(new URL(filename, parent)));
}

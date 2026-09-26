// CI greps for the SPA (spec §10.2, §10.3, §10.6). Fails with file:line for each hit.
//  1. no hex colours outside src/design/tokens.css
//  2. no physical-direction utilities (only logical: ms/me/ps/pe/start/end/text-start/text-end)
//  3. no Latin UI text in components: strings come from ar.json via t()
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const web = fileURLToPath(new URL("../web/", import.meta.url));
const src = join(web, "src");

function* files(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* files(path);
    else if (/\.(tsx?|css)$/.test(name)) yield path;
  }
}

const HEX = /#[0-9a-fA-F]{3,8}\b/;
const PHYSICAL =
  /(?<![\w-])(?:-?(?:ml|mr|pl|pr|left|right|border-l|border-r|rounded-l|rounded-r|rounded-tl|rounded-tr|rounded-bl|rounded-br|scroll-ml|scroll-mr|scroll-pl|scroll-pr)-[\w[]|text-(?:left|right)\b|float-(?:left|right)\b)/;
// JSX text between tags, and user-facing attributes, containing Latin letters.
const JSX_TEXT = />\s*([^<>{}]*[A-Za-z][^<>{}]*)\s*</;
const ATTR_TEXT = /\b(?:aria-label|title|placeholder|alt)="([^"]*[A-Za-z][^"]*)"/;

const problems = [];
for (const path of files(src)) {
  const rel = relative(web, path);
  const isTest = /\.test\.tsx?$/.test(path);
  readFileSync(path, "utf8")
    .split("\n")
    .forEach((line, i) => {
      const where = `web/${rel}:${i + 1}`;
      const code = line.replace(/\/\/.*$/, "").replace(/\/\*.*?\*\//g, "");
      if (!rel.endsWith("design/tokens.css") && HEX.test(code)) problems.push(`${where}: hex colour — use a token`);
      if (/\.tsx?$/.test(path) && PHYSICAL.test(code))
        problems.push(`${where}: physical direction utility — use ms/me/ps/pe/start/end`);
      if (path.endsWith(".tsx") && !isTest) {
        const text = JSX_TEXT.exec(code)?.[1] ?? ATTR_TEXT.exec(code)?.[1];
        if (text && !/^\s*$/.test(text) && !/[=&|?]|=>/.test(text))
          problems.push(`${where}: Latin UI text "${text.trim()}" — put it in ar.json`);
      }
    });
}

if (problems.length) {
  for (const p of problems) console.log(`::error::${p}`);
  console.error(`${problems.length} UI rule violation(s)`);
  process.exit(1);
}
console.log("UI checks passed: tokens only, logical direction, Arabic strings");

#!/usr/bin/env node
// Lightweight docs guardrail — keeps the brand casing consistent so it doesn't rot.
// Run: node scripts/docs-lint.mjs   (exits non-zero on a violation)
import {readdirSync, readFileSync} from 'node:fs';
import {join} from 'node:path';

const ROOTS = ['docs', 'docs-is', 'src'];
const EXT = /\.(md|mdx|tsx|ts)$/;
// Canonical brand is lowercase "minicloud". The only allowed "MiniCloud" is the
// stylised publication title "Carnets de MiniCloud".
const BAD_CASING = /(?<!Carnets de )MiniCloud/;

const violations = [];
for (const root of ROOTS) {
  let files;
  try {
    files = readdirSync(root, {recursive: true});
  } catch {
    continue;
  }
  for (const rel of files) {
    if (!EXT.test(rel)) continue;
    const path = join(root, rel);
    const lines = readFileSync(path, 'utf8').split('\n');
    lines.forEach((line, i) => {
      if (BAD_CASING.test(line)) {
        violations.push(`${path}:${i + 1}: ${line.trim().slice(0, 90)}`);
      }
    });
  }
}

if (violations.length) {
  console.error('❌  Brand casing: use lowercase "minicloud" (only "Carnets de MiniCloud" may keep the capital):');
  for (const v of violations) console.error('   ' + v);
  process.exit(1);
}
console.log('✓  docs-lint: brand casing OK');

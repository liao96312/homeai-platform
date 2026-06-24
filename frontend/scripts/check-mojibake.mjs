import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';

const projectRoot = path.resolve(import.meta.dirname, '..', '..');
const scanRoots = [
  path.join(projectRoot, 'frontend', 'src'),
  path.join(projectRoot, 'backend', 'app'),
  path.join(projectRoot, 'docs'),
];
const extensions = new Set(['.js', '.jsx', '.ts', '.tsx', '.py', '.md']);
const suspicious = /[璇鐧馃鈿鎰鏉灏鈫€绾楂杞闇鍐鎺鍙浼樓閿璁鏆鍒瀹鐢鏂涓骞鐩鍗妯瑙绯鑴]|�/;
const allowlist = [
  path.join(projectRoot, 'backend', 'app', 'services', 'seed.py'),
];

async function* walk(dir) {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(fullPath);
    } else if (extensions.has(path.extname(entry.name))) {
      yield fullPath;
    }
  }
}

const findings = [];
for (const root of scanRoots) {
  for await (const file of walk(root)) {
    if (allowlist.includes(file)) continue;
    const text = await readFile(file, 'utf8');
    text.split(/\r?\n/).forEach((line, index) => {
      if (suspicious.test(line)) {
        findings.push(`${path.relative(projectRoot, file)}:${index + 1}: ${line.trim()}`);
      }
    });
  }
}

if (findings.length) {
  console.error('Potential mojibake detected:');
  console.error(findings.join('\n'));
  process.exit(1);
}

console.log('Mojibake check passed');

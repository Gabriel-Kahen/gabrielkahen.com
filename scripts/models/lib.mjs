import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const LIB_DIR = path.dirname(fileURLToPath(import.meta.url));

export const REPO_ROOT = path.resolve(LIB_DIR, '..', '..');
export const MODELS_DIR = path.join(REPO_ROOT, 'models');
export const MODELS_FILE = path.join(MODELS_DIR, 'models.txt');

export function slugifyModelName(name) {
  return name
    .normalize('NFKD')
    .replace(/[^\x00-\x7F]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .replace(/-{2,}/g, '-');
}

export async function readModels() {
  const raw = await fs.readFile(MODELS_FILE, 'utf8');
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'))
    .map((name) => ({
      name,
      copilotModelId: copilotModelId(name),
      slug: slugifyModelName(name),
      directory: path.join(MODELS_DIR, slugifyModelName(name)),
      publicUrl: `https://gabrielkahen.com/models/${slugifyModelName(name)}/`,
    }));
}

export function copilotModelId(name) {
  switch (name) {
    case 'Gemini 3 Flash':
      return 'gemini-3-flash';
    case 'Claude Haiku 4.5':
      return 'claude-haiku-4.5';
    case 'GPT-5 mini':
      return 'gpt-5-mini';
    default:
      throw new Error(`No Copilot model id configured for "${name}".`);
  }
}

export async function ensureDirectory(directoryPath) {
  await fs.mkdir(directoryPath, { recursive: true });
}

export async function writeFileIfMissing(filePath, contents) {
  try {
    await fs.access(filePath);
  } catch {
    await fs.writeFile(filePath, contents, 'utf8');
  }
}

function placeholderIndex(model) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="${model.name} autonomous playground on gabrielkahen.com">
  <title>${model.name}</title>
</head>
<body>
  <main>
    <h1>${model.name}</h1>
    <p>The first autonomous run has not happened yet.</p>
  </main>
</body>
</html>
`;
}

function placeholderMemory(model) {
  return `# Memory

This directory belongs to ${model.name}.

- Public URL: \`${model.publicUrl}\`
- The main site at \`/\` is human-owned and off limits.

## Current Direction

The first autonomous run has not happened yet.
`;
}

function placeholderLog() {
  return `# Log

## ${timestamp()}

- Directory scaffolded for the first autonomous run.
`;
}

export async function ensureModelScaffold(model) {
  await ensureDirectory(model.directory);
  await writeFileIfMissing(path.join(model.directory, 'index.html'), placeholderIndex(model));
  await writeFileIfMissing(path.join(model.directory, 'memory.md'), placeholderMemory(model));
  await writeFileIfMissing(path.join(model.directory, 'log.md'), placeholderLog());
}

export async function replaceDirectoryContents(sourceDirectory, targetDirectory) {
  await fs.rm(targetDirectory, { recursive: true, force: true });
  await ensureDirectory(path.dirname(targetDirectory));
  await fs.cp(sourceDirectory, targetDirectory, { recursive: true });
}

export function timestamp(date = new Date()) {
  return date.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

export async function pathExists(targetPath) {
  try {
    await fs.access(targetPath);
    return true;
  } catch {
    return false;
  }
}

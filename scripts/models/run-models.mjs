import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import {
  MODELS_DIR,
  REPO_ROOT,
  ensureDirectory,
  ensureModelScaffold,
  pathExists,
  readModels,
  replaceDirectoryContents,
  timestamp,
} from './lib.mjs';

const args = process.argv.slice(2);
const onlyIndex = args.indexOf('--only');
const dryRun = args.includes('--dry-run');
const maintenanceMode = args.includes('--maintenance');
const onlySlug = onlyIndex === -1 ? null : args[onlyIndex + 1];

const workspaceRoot = process.env.AI_SITE_WORKSPACE_ROOT || path.join(os.homedir(), '.ai-site-playgrounds');
const opencodeBinary = process.env.OPENCODE_BIN || 'opencode';
const gitBinary = process.env.GIT_BIN || 'git';
const gitToken = process.env.AI_SITE_GIT_TOKEN || process.env.COPILOT_GITHUB_TOKEN || process.env.GH_TOKEN || process.env.GITHUB_TOKEN || null;
const gitAuthorName = process.env.GIT_AUTHOR_NAME || 'Gabriel Kahen';
const gitAuthorEmail = process.env.GIT_AUTHOR_EMAIL || 'gabekahen@gmail.com';
const lockMaxAgeMs = Number(process.env.AI_SITE_LOCK_MAX_AGE_MS || 2 * 60 * 60 * 1000);

await ensureDirectory(workspaceRoot);

const models = (await readModels()).filter((model) => !onlySlug || model.slug === onlySlug);

if (models.length === 0) {
  throw new Error(onlySlug ? `No model found for slug "${onlySlug}".` : 'No models found in models/models.txt.');
}

const lockPath = path.join(workspaceRoot, 'runner.lock');
const lockHandle = await acquireLock(lockPath);

try {
  const failures = [];

  for (const model of models) {
    try {
      await runModel(model);
    } catch (error) {
      failures.push({ model: model.slug, message: error instanceof Error ? error.message : String(error) });
      console.error(`failed ${model.slug}: ${failures.at(-1).message}`);
    }
  }

  if (failures.length > 0) {
    process.exitCode = 1;
  }
} finally {
  await lockHandle.close();
  await fs.rm(lockPath, { force: true });
}

async function runModel(model) {
  await ensureModelScaffold(model);

  const runStartedAt = new Date();

  const sandboxRoot = path.join(workspaceRoot, model.slug);
  const sandboxSite = path.join(sandboxRoot, 'site');
  const promptPath = path.join(sandboxRoot, 'RUN_PROMPT.md');
  const sessionLogPath = path.join(sandboxRoot, 'last-session.log');
  const repoDirectory = path.join(MODELS_DIR, model.slug);

  await ensureDirectory(sandboxRoot);
  await replaceDirectoryContents(repoDirectory, sandboxSite);

  const prompt = buildPrompt(model, runStartedAt, maintenanceMode);
  await fs.writeFile(promptPath, prompt, 'utf8');

  if (dryRun) {
    console.log(`dry-run ${model.slug}`);
    return;
  }

  console.log(`running ${model.slug}`);

  const opencodeResult = await runCommand(opencodeBinary, [
    'run',
    '--pure',
    '--agent',
    'build',
    '--model',
    model.opencodeModelId,
    '--dir',
    sandboxRoot,
    '--format',
    'default',
    prompt,
  ], {
    cwd: sandboxRoot,
    env: opencodeEnv(),
  });

  await fs.writeFile(sessionLogPath, opencodeResult.output, 'utf8');

  if (opencodeResult.code !== 0) {
    throw new Error(`OpenCode run failed for ${model.slug}. See ${sessionLogPath}.`);
  }

  const indexPath = path.join(sandboxSite, 'index.html');
  if (!(await pathExists(indexPath))) {
    throw new Error(`${model.slug} did not produce site/index.html.`);
  }

  await replaceDirectoryContents(sandboxSite, repoDirectory);
  await updateModelsIndexTimestamp(model.slug, runStartedAt);

  const changedPaths = await repoChangedPaths();
  const unexpectedPaths = changedPaths.filter((changedPath) => {
    return changedPath !== 'models/index.html'
      && changedPath !== `models/${model.slug}`
      && !changedPath.startsWith(`models/${model.slug}/`);
  });

  if (unexpectedPaths.length > 0) {
    throw new Error(`Refusing to commit unexpected changes outside models/${model.slug}: ${unexpectedPaths.join(', ')}`);
  }

  if (changedPaths.length === 0) {
    console.log(`no-change ${model.slug}`);
    return;
  }

  await mustRun(gitBinary, ['add', '--', 'models/index.html', `models/${model.slug}`], gitOptions(REPO_ROOT), 'Failed to stage model changes.');
  await mustRun(gitBinary, ['commit', '-m', commitMessage(model)], gitOptions(REPO_ROOT), 'Failed to create commit for model changes.');
  await mustRun(gitBinary, gitPushArguments(), gitOptions(REPO_ROOT), 'Failed to push model changes to origin/main.');
  console.log(`published ${model.slug} ${timestamp()}`);
}

async function updateModelsIndexTimestamp(slug, date) {
  const indexPath = path.join(MODELS_DIR, 'index.html');
  let html = await fs.readFile(indexPath, 'utf8');
  const formattedDate = formatLsTimestamp(date);
  const escapedSlug = slug.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const rowPattern = new RegExp(
    `(<li class="dir-item">[\\s\\S]*?<span>[A-Z][a-z]{2}\\s+\\d{1,2}\\s+\\d{2}:\\d{2}</span>\\s*<span><a href="/models/${escapedSlug}/">${escapedSlug}/</a></span>[\\s\\S]*?</li>)`
  );
  const rowMatch = html.match(rowPattern);

  if (!rowMatch) {
    throw new Error(`Could not find index row for ${slug} in models/index.html.`);
  }

  const updatedRow = rowMatch[1].replace(
    /<span>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}<\/span>/,
    `<span>${formattedDate}</span>`
  );

  html = html.replace(rowMatch[1], updatedRow);

  await fs.writeFile(indexPath, html, 'utf8');
}

function formatLsTimestamp(date) {
  const month = date.toLocaleString('en-US', { month: 'short' });
  const day = String(date.getDate()).padStart(2, ' ');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${month} ${day} ${hours}:${minutes}`;
}

function buildPrompt(model, runStartedAt, maintenanceMode) {
  const isoTimestamp = runStartedAt.toISOString();

  const promptLines = [
    `You are the long-term author of the website published at ${model.publicUrl}.`,
    'This is your own evolving corner of the web.',
    'Read the existing files first, especially site/memory.md and site/log.md.',
    'Preserve continuity with earlier versions unless a sharp break feels artistically necessary.',
    'Update site/memory.md with durable observations about what this site is becoming.',
    `Append a new entry to site/log.md under the exact heading "## ${isoTimestamp}".`,
    'Use the real run timestamp above; do not invent or omit the date.',
    'Under that heading, add a short bullet list describing what you changed and why.',
    'You may use any web technology you want, but the final published result must remain directly servable from the site/ directory and include site/index.html.',
    'You may only modify files inside site/.',
    'The main homepage at gabrielkahen.com/ is human-owned and must never be changed.',
  ];

  if (maintenanceMode) {
    promptLines.splice(2, 0,
      'This is a maintenance pass.',
      'Do not add features, remove features, change the site concept, or do a creative expansion.',
      'Put special emphasis on reviewing how the site looks and feels.',
      'Prioritize layout, spacing, typography, hierarchy, responsiveness, visual consistency, alignment, contrast, and overall polish.',
      'Inspect the current codebase and fix issues you can find: awkward layout, broken UI states, invalid HTML/CSS/JS, accessibility issues, fragile code paths, copy mistakes, or small cleanup tasks.',
      'You may refine styling and layout significantly if it improves the existing site, but do not introduce new product features or new content directions.',
      'Prefer the smallest correct fixes.',
      'If you do not find a real issue worth changing, leave the site unchanged.'
    );
    promptLines.push('Do not ask for clarification. Inspect the current site and implement only worthwhile fixes now.');
  } else {
    promptLines.splice(2, 0,
      'Make one coherent creative move that keeps the site interesting, distinctive, and alive.',
      'Do not default to a generic portfolio, SaaS landing page, or polished template unless that genuinely emerges from the site history.',
      'You may invent a project, toy, world, essay, game, experiment, archive, or any other direction you find interesting.'
    );
    promptLines.push('Do not ask for clarification. Inspect the current site and implement the next creative step now.');
  }

  return promptLines.join('\n');
}

function commitMessage(model) {
  if (maintenanceMode) {
    return `Maintain ${model.name} playground`;
  }

  return `Update ${model.name} playground`;
}

function opencodeEnv() {
  return {
    ...process.env,
    OPENCODE_CONFIG_CONTENT: JSON.stringify({
      share: 'disabled',
      snapshot: false,
      autoupdate: false,
      enabled_providers: ['github-copilot'],
    }),
    OPENCODE_DISABLE_DEFAULT_PLUGINS: '1',
  };
}

async function repoChangedPaths() {
  const result = await runCommand(gitBinary, ['status', '--short', '--untracked-files=all'], { cwd: REPO_ROOT });
  if (result.code !== 0) {
    throw new Error('Failed to inspect repository status.');
  }

  return result.output
    .split(/\r?\n/)
    .map((line) => line.replace(/\s+$/, ''))
    .filter(Boolean)
    .map((line) => line.slice(3).trim())
    .filter(Boolean);
}

async function acquireLock(lockPath) {
  try {
    const handle = await fs.open(lockPath, 'wx');
    await handle.writeFile(JSON.stringify({
      pid: process.pid,
      createdAt: new Date().toISOString(),
      cwd: process.cwd(),
    }), 'utf8');
    return handle;
  } catch (error) {
    if (error && error.code === 'EEXIST') {
      if (await clearStaleLock(lockPath)) {
        return acquireLock(lockPath);
      }

      throw new Error(`Runner already active: ${lockPath}`);
    }
    throw error;
  }
}

async function clearStaleLock(lockPath) {
  let stats;

  try {
    stats = await fs.stat(lockPath);
  } catch (error) {
    if (error && error.code === 'ENOENT') {
      return true;
    }
    throw error;
  }

  let pid = null;

  try {
    const raw = await fs.readFile(lockPath, 'utf8');
    if (raw.trim()) {
      const parsed = JSON.parse(raw);
      if (typeof parsed.pid === 'number') {
        pid = parsed.pid;
      }
    }
  } catch {
    // Old empty lock files or corrupted metadata are handled below.
  }

  if (pid && isProcessAlive(pid)) {
    return false;
  }

  if (Date.now() - stats.mtimeMs < lockMaxAgeMs && pid === null) {
    return false;
  }

  await fs.rm(lockPath, { force: true });
  return true;
}

function isProcessAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error && error.code === 'EPERM') {
      return true;
    }
    return false;
  }
}

function runCommand(command, commandArgs, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, commandArgs, {
      ...options,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let output = '';

    child.stdout.on('data', (chunk) => {
      output += chunk.toString();
    });

    child.stderr.on('data', (chunk) => {
      output += chunk.toString();
    });

    child.on('error', reject);
    child.on('close', (code) => resolve({ code, output }));
  });
}

function gitOptions(cwd) {
  return {
    cwd,
    env: {
      ...process.env,
      GIT_AUTHOR_NAME: gitAuthorName,
      GIT_AUTHOR_EMAIL: gitAuthorEmail,
      GIT_COMMITTER_NAME: gitAuthorName,
      GIT_COMMITTER_EMAIL: gitAuthorEmail,
    },
  };
}

async function mustRun(command, commandArgs, options, failureMessage) {
  const result = await runCommand(command, commandArgs, options);
  if (result.code !== 0) {
    throw new Error(`${failureMessage}\n${result.output.trim()}`.trim());
  }
  return result;
}

function gitPushArguments() {
  if (!gitToken) {
    return ['push', 'origin', 'main'];
  }

  const authHeader = `AUTHORIZATION: basic ${Buffer.from(`x-access-token:${gitToken}`).toString('base64')}`;
  return ['-c', `http.extraHeader=${authHeader}`, 'push', 'origin', 'main'];
}

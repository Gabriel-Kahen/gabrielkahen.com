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
const onlySlug = onlyIndex === -1 ? null : args[onlyIndex + 1];

const workspaceRoot = process.env.AI_SITE_WORKSPACE_ROOT || path.join(os.homedir(), '.ai-site-playgrounds');
const copilotBinary = process.env.COPILOT_BIN || 'copilot';
const gitBinary = process.env.GIT_BIN || 'git';
const gitToken = process.env.AI_SITE_GIT_TOKEN || process.env.COPILOT_GITHUB_TOKEN || process.env.GH_TOKEN || process.env.GITHUB_TOKEN || null;

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

  const sandboxRoot = path.join(workspaceRoot, model.slug);
  const sandboxSite = path.join(sandboxRoot, 'site');
  const promptPath = path.join(sandboxRoot, 'RUN_PROMPT.md');
  const sessionLogPath = path.join(sandboxRoot, 'last-session.log');
  const repoDirectory = path.join(MODELS_DIR, model.slug);

  await ensureDirectory(sandboxRoot);
  await replaceDirectoryContents(repoDirectory, sandboxSite);

  const prompt = buildPrompt(model);
  await fs.writeFile(promptPath, prompt, 'utf8');

  if (dryRun) {
    console.log(`dry-run ${model.slug}`);
    return;
  }

  console.log(`running ${model.slug}`);

  const copilotResult = await runCommand(copilotBinary, [
    '-p',
    prompt,
    '--model',
    model.copilotModelId,
    '--add-dir',
    sandboxRoot,
    '--allow-tool=write',
    '--allow-tool=shell',
    '--deny-tool=shell(git)',
    '--deny-tool=shell(gh)',
    '--deny-tool=shell(ssh)',
    '--deny-tool=shell(scp)',
    '--deny-tool=shell(rsync)',
    '--deny-tool=shell(sudo)',
  ], {
    cwd: sandboxRoot,
    env: process.env,
  });

  await fs.writeFile(sessionLogPath, copilotResult.output, 'utf8');

  if (copilotResult.code !== 0) {
    throw new Error(`Copilot run failed for ${model.slug}. See ${sessionLogPath}.`);
  }

  const indexPath = path.join(sandboxSite, 'index.html');
  if (!(await pathExists(indexPath))) {
    throw new Error(`${model.slug} did not produce site/index.html.`);
  }

  await replaceDirectoryContents(sandboxSite, repoDirectory);

  const changedPaths = await repoChangedPaths();
  const unexpectedPaths = changedPaths.filter((changedPath) => {
    return changedPath !== `models/${model.slug}` && !changedPath.startsWith(`models/${model.slug}/`);
  });

  if (unexpectedPaths.length > 0) {
    throw new Error(`Refusing to commit unexpected changes outside models/${model.slug}: ${unexpectedPaths.join(', ')}`);
  }

  if (changedPaths.length === 0) {
    console.log(`no-change ${model.slug}`);
    return;
  }

  await mustRun(gitBinary, ['add', '--', `models/${model.slug}`], { cwd: REPO_ROOT }, 'Failed to stage model changes.');
  await mustRun(gitBinary, ['commit', '-m', `Update ${model.name} playground`], { cwd: REPO_ROOT }, 'Failed to create commit for model changes.');
  await mustRun(gitBinary, gitPushArguments(), { cwd: REPO_ROOT }, 'Failed to push model changes to origin/main.');
  console.log(`published ${model.slug} ${timestamp()}`);
}

function buildPrompt(model) {
  return [
    `You are the long-term author of the website published at ${model.publicUrl}.`,
    'This is your own evolving corner of the web.',
    'Make one coherent creative move that keeps the site interesting, distinctive, and alive.',
    'Do not default to a generic portfolio, SaaS landing page, or polished template unless that genuinely emerges from the site history.',
    'You may invent a project, toy, world, essay, game, experiment, archive, or any other direction you find interesting.',
    'Read the existing files first, especially site/memory.md and site/log.md.',
    'Preserve continuity with earlier versions unless a sharp break feels artistically necessary.',
    'Update site/memory.md with durable observations about what this site is becoming.',
    'Append a short entry to site/log.md describing what you changed and why.',
    'You may use any web technology you want, but the final published result must remain directly servable from the site/ directory and include site/index.html.',
    'You may only modify files inside site/.',
    'The main homepage at gabrielkahen.com/ is human-owned and must never be changed.',
    'Do not ask for clarification. Inspect the current site and implement the next creative step now.',
  ].join('\n');
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
    return await fs.open(lockPath, 'wx');
  } catch (error) {
    if (error && error.code === 'EEXIST') {
      throw new Error(`Runner already active: ${lockPath}`);
    }
    throw error;
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

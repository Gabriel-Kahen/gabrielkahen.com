import { ensureModelScaffold, readModels } from './lib.mjs';

const models = await readModels();

for (const model of models) {
  await ensureModelScaffold(model);
  console.log(`ready ${model.slug}`);
}

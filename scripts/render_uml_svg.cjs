// Render UML DOT files locally with the existing Graphviz WASM package.
const fs = require('node:fs/promises');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'docs', 'uml');
(async () => {
  const viz = await require(path.join(root, 'artifacts/ai/erd-tools/node_modules/@viz-js/viz')).instance();
  for (const name of (await fs.readdir(out)).filter(name => name.endsWith('.dot'))) {
    const result = viz.render(await fs.readFile(path.join(out, name), 'utf8'), {format: 'svg', engine: 'dot'});
    if (result.status !== 'success') throw Error(JSON.stringify(result.errors));
    await fs.writeFile(path.join(out, name.replace(/\.dot$/, '.svg')), result.output);
    process.stdout.write(name + ' rendered\n');
  }
})().catch(error => {process.stderr.write(String(error)); process.exitCode = 1;});

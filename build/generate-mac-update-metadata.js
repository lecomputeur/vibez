const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

function fileMetadata(filePath) {
  return {
    sha512: crypto.createHash('sha512').update(fs.readFileSync(filePath)).digest('base64'),
    size: fs.statSync(filePath).size,
  };
}

function generateMacUpdateMetadata(outputDirectory, version, releaseDate = new Date().toISOString()) {
  const architectures = ['x64', 'arm64'];
  const files = architectures.map((arch) => {
    const name = `VibeZ-${version}-macOS-${arch}.zip`;
    const filePath = path.join(outputDirectory, name);
    if (!fs.existsSync(filePath)) throw new Error(`Missing macOS update archive: ${filePath}`);
    return { name, ...fileMetadata(filePath) };
  });
  const primary = files[0];
  const lines = [
    `version: ${version}`,
    'files:',
    ...files.flatMap((file) => [
      `  - url: ${file.name}`,
      `    sha512: ${file.sha512}`,
      `    size: ${file.size}`,
    ]),
    `path: ${primary.name}`,
    `sha512: ${primary.sha512}`,
    `releaseDate: '${releaseDate}'`,
    '',
  ];
  const metadataPath = path.join(outputDirectory, 'latest-mac.yml');
  fs.writeFileSync(metadataPath, lines.join('\n'));
  return metadataPath;
}

if (require.main === module) {
  const outputDirectory = path.resolve(process.argv[2] || 'release-assets');
  const version = process.argv[3] || require('../package.json').version;
  const metadataPath = generateMacUpdateMetadata(outputDirectory, version, process.env.VIBEZ_RELEASE_DATE);
  console.log(`Created ${metadataPath}`);
}

module.exports = { generateMacUpdateMetadata };

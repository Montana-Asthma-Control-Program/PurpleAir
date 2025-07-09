const fs = require('fs');
const path = require('path');
const readline = require('readline');

/**
 * Read the last non-empty line from a CSV file and parse it into a JSON object
 * Assumes the first line of the CSV is a header
 */
async function readLastCSVRecord(filePath) {
  return new Promise((resolve, reject) => {
    const input = fs.createReadStream(filePath, { encoding: 'utf8' });

    const lines = [];
    const rl = readline.createInterface({ input });

    rl.on('line', (line) => {
      if (line.trim()) {
        lines.push(line);
        if (lines.length > 2) lines.shift(); // keep only last 2 lines
      }
    });

    rl.on('close', () => {
      if (lines.length < 2) return reject(new Error('Not enough lines in file'));
      const [header, last] = lines;
      const keys = header.split(',');
      const values = last.split(',');
      const record = Object.fromEntries(keys.map((k, i) => [k, values[i]]));
      resolve(record);
    });

    rl.on('error', reject);
  });
}

/**
 * Given a directory, read the last CSV record from each file
 */
async function readLatestRecordsFromCSVDirectory(dirPath) {
  const files = fs.readdirSync(dirPath).filter(f => f.endsWith('.csv'));
  const result = {};

  for (const file of files) {
    try {
      const fullPath = path.join(dirPath, file);
      const record = await readLastCSVRecord(fullPath);
      result[file] = record;
    } catch (err) {
      console.error(`Error reading ${file}: ${err.message}`);
    }
  }

  return result;
}

// Example usage:
// (async () => {
//   const records = await readLatestRecordsFromCSVDirectory('./csv-folder');
//   console.log(records);
// })();

module.exports = { readLatestRecordsFromCSVDirectory };

// At the end of readLastCSVRecord.js
window.readLatestRecordsFromCSVDirectory = readLatestRecordsFromCSVDirectory;

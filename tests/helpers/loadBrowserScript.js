const fs = require('node:fs');
const path = require('node:path');

/**
 * Loads and executes a browser-style JS file (IIFE attaching to window) into the current JSDOM window.
 * It does NOT use eval globally; instead it wraps the file contents in a Function and passes the jsdom window.
 * @param {string} filePath Absolute or relative path to the JS file.
 */
function loadBrowserScript(filePath) {
  const absolutePath = path.isAbsolute(filePath) ? filePath : path.resolve(process.cwd(), filePath);
  const code = fs.readFileSync(absolutePath, 'utf8');
  const runner = new Function('window', 'document', `${code}\n//# sourceURL=${absolutePath}`);
  runner(window, document);
}

module.exports = { loadBrowserScript };

#!/usr/bin/env node
/**
 * Render Frontend Build Script: Generates client runtime environment config (env.js)
 * Supports BACKEND_API_URL, API_BASE_URL, and RENDER_EXTERNAL_URL environment variables.
 */
const fs = require('fs');
const path = require('path');

let backendUrl = (
    process.env.BACKEND_API_URL ||
    process.env.API_BASE_URL ||
    process.env.RENDER_EXTERNAL_URL ||
    ''
).trim();

// If backendUrl is provided without protocol, prepend https://
if (backendUrl && !/^https?:\/\//i.test(backendUrl)) {
    backendUrl = (backendUrl.startsWith('localhost') || backendUrl.startsWith('127.0.0.1'))
        ? 'http://' + backendUrl
        : 'https://' + backendUrl;
}

// Strip trailing slash
if (backendUrl.endsWith('/')) {
    backendUrl = backendUrl.slice(0, -1);
}

const envFileContent = `// Auto-generated client runtime environment configuration
(function() {
    window.__ENV__ = window.__ENV__ || {};
    window.__ENV__.BACKEND_API_URL = "${backendUrl}";
    if (!window.BACKEND_API_URL && "${backendUrl}") {
        window.BACKEND_API_URL = "${backendUrl}";
    }
})();
`;

const targetFiles = [
    path.join(__dirname, '..', 'frontend', 'static', 'js', 'env.js'),
    path.join(__dirname, '..', 'frontend', 'env.js'),
    path.join(__dirname, '..', 'app', 'static', 'js', 'env.js')
];

targetFiles.forEach(targetFile => {
    try {
        const parentDir = path.dirname(targetFile);
        if (!fs.existsSync(parentDir)) {
            fs.mkdirSync(parentDir, { recursive: true });
        }
        fs.writeFileSync(targetFile, envFileContent, 'utf8');
        console.log(`[build-env] Injected BACKEND_API_URL to: ${targetFile}`);
    } catch (err) {
        console.warn(`[build-env] Warning writing to ${targetFile}:`, err.message);
    }
});

console.log(`[build-env] Final client BACKEND_API_URL: "${backendUrl || '(same-origin / auto-detect)'}"`);

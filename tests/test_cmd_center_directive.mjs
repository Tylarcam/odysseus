/**
 * Directive triage peek/cycle helpers.
 * Run: node --test tests/test_cmd_center_directive.mjs
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = readFileSync(join(root, 'static/js/cmdCenterDirective.js'), 'utf8');

function loadNextPeekIndex() {
  const start = src.indexOf('export function nextPeekIndex');
  assert.ok(start >= 0, 'nextPeekIndex must be exported');
  const brace = src.indexOf('{', start);
  let depth = 0;
  let end = brace;
  for (; end < src.length; end++) {
    if (src[end] === '{') depth += 1;
    else if (src[end] === '}') {
      depth -= 1;
      if (depth === 0) {
        end += 1;
        break;
      }
    }
  }
  const fnSrc = src.slice(start, end).replace(/^export /, '');
  return new Function(`${fnSrc}; return nextPeekIndex;`)();
}

function cyclePeekBody() {
  const start = src.indexOf('function _cyclePeek');
  assert.ok(start >= 0, '_cyclePeek must exist');
  const brace = src.indexOf('{', start);
  let depth = 0;
  let end = brace;
  for (; end < src.length; end++) {
    if (src[end] === '{') depth += 1;
    else if (src[end] === '}') {
      depth -= 1;
      if (depth === 0) {
        end += 1;
        break;
      }
    }
  }
  return src.slice(start, end);
}

test('nextPeekIndex walks forward and wraps the deck', () => {
  const nextPeekIndex = loadNextPeekIndex();
  assert.equal(nextPeekIndex(0, 3), 1);
  assert.equal(nextPeekIndex(1, 3), 2);
  assert.equal(nextPeekIndex(2, 3), 0);
  assert.equal(nextPeekIndex(0, 1), 0);
  assert.equal(nextPeekIndex(0, 0), 0);
});

test('peek cycle does not delegate, finish, or drop the card', () => {
  const body = cyclePeekBody();
  assert.match(body, /nextPeekIndex\(_index,\s*_stack\.length\)/);
  assert.match(body, /_paintCard\(\{\s*peek:\s*true\s*\}\)/);
  assert.doesNotMatch(body, /splice|_delegate|_finish|_onRefresh/);
});

test('double-tap peeks; swipe left/right still act', () => {
  assert.match(src, /DOUBLE_TAP_MS\s*=\s*500/);
  assert.match(src, /DOUBLE_TAP_PX\s*=\s*40/);
  assert.match(src, /_cyclePeek\(\)/);
  assert.match(src, /addEventListener\('dblclick'/);
  assert.match(src, /lastTapT && \(now - lastTapT\) < DOUBLE_TAP_MS/);
  // Swipe commit paths must still fire actions, not peek
  assert.match(src, /translateX\(-120%\)[\s\S]*_delegate\(\)/);
  assert.match(src, /translateX\(120%\)[\s\S]*_finish\(\)/);
  assert.match(src, /double tap to peek next/);
});

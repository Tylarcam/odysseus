/**
 * Cmd Center editable-focus helpers — preserve caret across innerHTML paints.
 * Run: node --test tests/test_cmd_center_focus.mjs
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const focusSrc = readFileSync(join(root, 'static/js/cmdCenterFocus.js'), 'utf8');
const cmdSrc = readFileSync(join(root, 'static/js/cmdCenter.js'), 'utf8');

test('cmdCenterFocus exports capture / restore / owns helpers', () => {
  assert.match(focusSrc, /export function isCmdEditableTarget/);
  assert.match(focusSrc, /export function cmdEditableOwnsFocus/);
  assert.match(focusSrc, /export function captureCmdEditableFocus/);
  assert.match(focusSrc, /export function restoreCmdEditableFocus/);
  assert.match(focusSrc, /preventScroll:\s*true/);
  assert.match(focusSrc, /setSelectionRange/);
  // Helper focuses the editable only — never a toast/status region
  assert.doesNotMatch(focusSrc, /toast.*\.focus|getElementById\(['\"]toast['\"]\)/);
});

test('cmdCenter wires focus helpers into paint + live update paths', () => {
  assert.match(cmdSrc, /from '\.\/cmdCenterFocus\.js'/);
  assert.match(cmdSrc, /cmdEditableOwnsFocus\(\)/);
  assert.match(cmdSrc, /captureCmdEditableFocus\(\)/);
  assert.match(cmdSrc, /restoreCmdEditableFocus\(/);
  // Live update must defer full _paint while an editable owns focus
  assert.match(
    cmdSrc,
    /if\s*\(!cardsUpdated\)\s*\{[^}]*cmdEditableOwnsFocus\(\)[^}]*return;/s
  );
  // Rail paint skips destructive innerHTML while typing
  assert.match(
    cmdSrc,
    /function _paintDomainRails[\s\S]*?if\s*\(cmdEditableOwnsFocus\(\)\)\s*\{[\s\S]*?return;/
  );
  // Full _paint restores caret after rebuild
  assert.match(
    cmdSrc,
    /function _paint\(\)\s*\{[\s\S]*?captureCmdEditableFocus\(\)[\s\S]*?restoreCmdEditableFocus\(focusSnap\);/
  );
});

test('global Space/Esc still ignore editable targets via _inputOwnsFocus', () => {
  assert.match(cmdSrc, /function _inputOwnsFocus\(\)/);
  assert.match(cmdSrc, /if\s*\(_inputOwnsFocus\(\)\)\s*return;/);
});

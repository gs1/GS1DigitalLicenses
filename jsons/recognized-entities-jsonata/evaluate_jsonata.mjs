#!/usr/bin/env node
/**
 * Evaluates a JSONata expression against an input JSON document.
 *
 * Usage:
 *   node evaluate_jsonata.mjs <expression.jsonata> <input.json>
 *
 * Outputs the result as JSON to stdout.
 *
 * Requires: npm install jsonata
 */

import { readFileSync } from 'fs';
import jsonata from 'jsonata';

const [,, exprPath, inputPath] = process.argv;

if (!exprPath || !inputPath) {
  console.error('Usage: node evaluate_jsonata.mjs <expression.jsonata> <input.json>');
  process.exit(1);
}

const expression = readFileSync(exprPath, 'utf8');
const input = JSON.parse(readFileSync(inputPath, 'utf8'));

const compiled = jsonata(expression);
const result = await compiled.evaluate(input);

console.log(JSON.stringify(result, null, 2));

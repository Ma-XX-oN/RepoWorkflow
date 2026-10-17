/** Reusable executable-interface recorder, verifier and player (RWF #670).
 * No network, DOM, repo runtime or production dependencies.
 * Compatible with the grammar specified by RepoWorkflow #518/#553.
 */
import { readFile } from 'node:fs/promises';
import { createReadStream, createWriteStream } from 'node:fs';
import { createInterface } from 'node:readline';
import { once } from 'node:events';
import { isDeepStrictEqual } from 'node:util';
import { identityEntry, identityRecording, JsonlReader } from './interface-stream.mjs';

export const Free = Symbol('interface-playback.Free');
const allowed = new Set(['$free', '$unchanged', '$new', '$ref', '$type']);
const plain = v => v !== null && typeof v === 'object' &&
  (Object.getPrototypeOf(v) === Object.prototype || Object.getPrototypeOf(v) === null);
const own = (v, k) => Object.prototype.hasOwnProperty.call(v, k);
const failure = (path, description) => { throw new Error(`${path}: ${description}`); };

function check(value, path = 'value') {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return;
  if (typeof value === 'number' && Number.isFinite(value)) return;
  if (Array.isArray(value)) {
    value.forEach((v, i) => check(v, `${path}[${i}]`));
    return;
  }
  if (!plain(value)) failure(path, 'unsupported non-JSON value');
  for (const [k, v] of Object.entries(value)) {
    if (['__proto__', 'prototype', 'constructor'].includes(k)) failure(path, `forbidden key ${k}`);
    if (k.startsWith('$') && !allowed.has(k)) failure(path, `unknown reserved key ${k}`);
    check(v, `${path}.${k}`);
  }
  if (own(value, '$new') && own(value, '$ref')) failure(path, 'conflicting logical identity');
  if (own(value, '$new') || own(value, '$ref')) {
    const id = value.$new ?? value.$ref;
    if (typeof id !== 'string' || !id) failure(path, 'invalid logical object id');
  }
  if (own(value, '$type') && (typeof value.$type !== 'string' || !value.$type)) failure(path, 'invalid type');
  if (own(value, '$free') && (Object.keys(value).length !== 1 || value.$free !== true)) failure(path, 'invalid Free');
  if (own(value, '$unchanged')) {
    const q = value.$unchanged;
    if (Object.keys(value).length !== 1 ||
        (q !== true && !(plain(q) && Object.keys(q).length === 1 &&
        Array.isArray(q.keys) && q.keys.every(k => typeof k === 'string')))) {
      failure(path, 'invalid Unchanged');
    }
  }
  if (own(value, 'keys') && own(value, '$type') && value.$type === 'builtins.dict') {
    if (!Array.isArray(value.keys) || !value.keys.every(k => typeof k === 'string')) {
      failure(path, 'invalid dictionary keys');
    }
  }
}

export function validateInteraction(entry, index = 0) {
  const path = `interaction[${index}]`;
  check(entry, path);
  if (!plain(entry) || !plain(entry.call) || !plain(entry.before) ||
      !plain(entry.after) || !plain(entry.result)) failure(path, 'missing call/before/after/result');
  if (typeof entry.call.fn_name !== 'string' || !entry.call.fn_name) failure(path, 'invalid function name');
  if (!own(entry.call, 'obj') || !Array.isArray(entry.before.args) ||
      !Array.isArray(entry.after.args) || !plain(entry.before.kwargs) ||
      !plain(entry.after.kwargs)) failure(path, 'invalid call structure');
  if (entry.before.args.length !== entry.after.args.length) failure(path, 'args length changed');
  if (own(entry.result, 'return') === own(entry.result, 'raise')) failure(path, 'exactly one return or raise required');
  const free = plain(entry.call.obj) && entry.call.obj.$free === true;
  if (free && (own(entry.before, 'obj') || own(entry.after, 'obj'))) failure(path, 'Free cannot have receiver state');
  if (!free && (!own(entry.before, 'obj') || !own(entry.after, 'obj'))) failure(path, 'receiver states missing');
  return entry;
}

const copy = v => structuredClone(v);
const isObject = v => v !== null && typeof v === 'object';
const typeName = v => Array.isArray(v) ? 'builtins.list' : plain(v) ? 'builtins.dict' :
  v.constructor?.name || 'Object';

export class InterfacePlayback {
  constructor({ types = {}, interactions = [] } = {}) {
    this.types = { ...types };
    this.entries = [];
    this.stream = null;
    this.cursor = 0;
    this.recordNames = new WeakMap();
    this.recordCount = 0;
    this.references = new Map();
    if (interactions.length) this.load(interactions);
  }

  reset() {
    this.cursor = 0;
    this.references.clear();
    if (this.stream) this.stream.reset();
  }

  async load(source) {
    if (this.stream) { this.stream.close(); this.stream = null; }
    if (typeof source === 'string' && !source.endsWith('.json')) {
      const names = new Set();
      const validate = (entry, index) => {
        validateInteraction(entry, index);
        identityEntry(entry, names, index);
      };
      // Validate the entire recording without retaining interactions.
      const scan = new JsonlReader(source, validate);
      try {
        while (scan.peek() !== undefined) scan.advance();
      } finally { scan.close(); }
      this.entries = [];
      this.stream = new JsonlReader(source, validateInteraction);
      this.reset();
      return this;
    }
    const data = typeof source === 'string' ?
      JSON.parse(await readFile(source, 'utf8')) : source;
    if (!Array.isArray(data)) failure('load', 'expected interaction array or JSONL file');
    data.forEach((entry, i) => validateInteraction(entry, i));
    identityRecording(data);
    this.entries = copy(data);
    this.reset();
    return this;
  }

  async save(path) {
    if (!this.stream) {
      this.entries.forEach((entry, i) => validateInteraction(entry, i));
      identityRecording(this.entries);
    }
    const output = createWriteStream(path, { encoding: 'utf8' });
    try {
      const records = this.stream ? this.stream.records() : this.entries;
      for (const entry of records) {
        if (!output.write(`${JSON.stringify(entry)}\n`)) await once(output, 'drain');
      }
      output.end();
      await once(output, 'finish');
    } catch (error) {
      output.destroy();
      throw error;
    }
  }

  #encode(v, seen = new WeakSet()) {
    if (!isObject(v)) {
      if (typeof v === 'number' && !Number.isFinite(v)) failure('record', 'nonfinite number');
      if (v === undefined || ['function', 'symbol', 'bigint'].includes(typeof v)) {
        failure('record', 'unsupported runtime value');
      }
      return v;
    }
    if (v instanceof Map || v instanceof Set || v instanceof Date ||
        ArrayBuffer.isView(v) || v instanceof ArrayBuffer) {
      failure('record', 'unsupported runtime object type');
    }
    if (this.recordNames.has(v)) {
      const id = this.recordNames.get(v);
      if (seen.has(v)) return { $ref: id };
      seen.add(v);
      return this.#describe(v, { $ref: id }, seen);
    }
    const id = `object_${++this.recordCount}`;
    this.recordNames.set(v, id);
    seen.add(v);
    return this.#describe(v, { $new: id, $type: typeName(v) }, seen);
  }

  #describe(v, identity, seen) {
    if (Array.isArray(v)) return { ...identity, items: v.map(item => this.#encode(item, seen)) };
    if (plain(v)) {
      const items = {};
      for (const [k, value] of Object.entries(v)) items[k] = this.#encode(value, seen);
      return { ...identity, keys: Object.keys(v), items };
    }
    const out = { ...identity };
    for (const [k, value] of Object.entries(v)) out[k] = this.#encode(value, seen);
    return out;
  }

  #snapshot(receiver, args, kwargs, seen = new WeakSet()) {
    const result = { args: args.map(a => this.#encode(a, seen)), kwargs: {} };
    for (const [key, value] of Object.entries(kwargs)) result.kwargs[key] = this.#encode(value, seen);
    if (receiver !== Free) result.obj = this.#encode(receiver, seen);
    return result;
  }

  async record(filter, invoke, receiver, functionName, args = [], kwargs = {}) {
    if (typeof filter !== 'function' || typeof invoke !== 'function') failure('record', 'expected filter and function');
    if (!Array.isArray(args) || !plain(kwargs)) failure('record', 'invalid args/kwargs');
    const identity = receiver === Free ? { $free: true } : (() => {
      if (this.recordNames.has(receiver)) {
        return { $ref: this.recordNames.get(receiver) };
      }
      const id = `object_${++this.recordCount}`;
      this.recordNames.set(receiver, id);
      return { $new: id, $type: typeName(receiver) };
    })();
    const call = { fn_name: functionName, obj: receiver === Free ? identity :
      identity };
    const before = this.#snapshot(receiver, args, kwargs);
    let value, thrown;
    try { value = await invoke(...args, ...(Object.keys(kwargs).length ? [kwargs] : [])); } catch (error) { thrown = error; }
    const after = this.#snapshot(receiver, args, kwargs);
    const result = thrown ? { raise: { $type: thrown.constructor?.name || 'Error', args: [String(thrown.message)] } } :
      { return: this.#encode(value) };
    const entry = filter({ call, before, after, result });
    validateInteraction(entry, this.entries.length);
    if (this.stream) failure('record', 'cannot append to loaded streaming source');
    this.entries.push(copy(entry));
    if (thrown) throw thrown;
    return value;
  }

  #expect(receiver, name, args, kwargs) {
    const entry = this.stream ? this.stream.peek() : this.entries[this.cursor];
    if (!entry) failure(`interaction[${this.cursor}]`, 'recording exhausted');
    if (entry.call.fn_name !== name) failure(`interaction[${this.cursor}].call`,
      `expected ${entry.call.fn_name}, received ${name}`);
    const free = receiver === Free;
    if (free !== (entry.call.obj?.$free === true)) failure(`interaction[${this.cursor}].call.obj`, 'receiver kind mismatch');
    if (args.length !== entry.before.args.length) failure('before.args', 'argument length mismatch');
    if (Object.keys(kwargs).sort().join() !== Object.keys(entry.before.kwargs).sort().join()) {
      failure('before.kwargs', 'keyword keys mismatch');
    }
    const refs = new Map(this.references);
    this.#compare(entry.call.obj, receiver, refs, 'call.obj', free);
    this.#compare(entry.before.obj, receiver, refs, 'before.obj', free);
    args.forEach((value, i) => this.#compare(entry.before.args[i], value, refs, `before.args[${i}]`));
    for (const [k, v] of Object.entries(kwargs)) this.#compare(entry.before.kwargs[k], v, refs, `before.kwargs.${k}`);
    return { entry, refs };
  }

  #compare(spec, actual, refs, path, skip = false) {
    if (skip) return;
    if (spec === null || typeof spec !== 'object') {
      if (!Object.is(spec, actual)) failure(path, 'value mismatch');
      return;
    }
    if (Array.isArray(spec)) {
      if (!Array.isArray(actual) || actual.length !== spec.length) failure(path, 'array mismatch');
      spec.forEach((v, i) => this.#compare(v, actual[i], refs, `${path}[${i}]`));
      return;
    }
    if (own(spec, '$unchanged')) return;
    if (own(spec, '$free')) return;
    if (!isObject(actual)) failure(path, 'expected object');
    const id = spec.$new ?? spec.$ref;
    if (spec.$new) {
      if (refs.has(id)) failure(path, `duplicate $new ${id}`);
      for (const [otherId, value] of refs) {
        if (value === actual) failure(path, `distinct logical identities ${otherId} and ${id} alias`);
      }
      refs.set(id, actual);
    }
    if (spec.$ref && (!refs.has(id) || refs.get(id) !== actual)) failure(path, `identity mismatch ${id}`);
    if (spec.$type && typeName(actual) !== spec.$type) failure(path, `type mismatch ${spec.$type}`);
    if (spec.$type === 'builtins.list' || (own(spec, 'items') && Array.isArray(spec.items))) {
      if (!Array.isArray(actual) || actual.length !== spec.items.length) failure(path, 'list length mismatch');
      spec.items.forEach((v, i) => this.#compare(v, actual[i], refs, `${path}[${i}]`));
    } else if (spec.$type === 'builtins.dict' || own(spec, 'keys') || (plain(spec.items) && !Array.isArray(spec.items))) {
      if (!plain(actual)) failure(path, 'expected plain dictionary');
      if (spec.keys && Object.keys(actual).join('\u0000') !== spec.keys.join('\u0000')) failure(path, 'dictionary keys mismatch');
      for (const [k, v] of Object.entries(spec.items || {})) {
        if (!own(actual, k)) failure(path, `missing key ${k}`);
        this.#compare(v, actual[k], refs, `${path}.${k}`);
      }
    } else {
      for (const [k, v] of Object.entries(spec)) {
        if (k.startsWith('$')) continue;
        if (!own(actual, k)) failure(path, `missing property ${k}`);
        this.#compare(v, actual[k], refs, `${path}.${k}`);
      }
    }
  }

  #checkUnchanged(spec, actual, baseline, path) {
    if (!isObject(spec)) return;
    if (own(spec, '$unchanged')) {
      const selected = spec.$unchanged;
      if (selected === true) {
        if (!isDeepStrictEqual(actual, baseline)) failure(path, 'Unchanged invariant violated');
      } else {
        for (const key of selected.keys) {
          if (!isObject(actual) || !isObject(baseline) ||
              !own(actual, key) || !own(baseline, key) ||
              !isDeepStrictEqual(actual[key], baseline[key])) {
            failure(`${path}.${key}`, 'selected Unchanged invariant violated');
          }
        }
      }
      return;
    }
    if (Array.isArray(spec)) {
      spec.forEach((item, i) => this.#checkUnchanged(item, actual?.[i], baseline?.[i], `${path}[${i}]`));
    } else if (Array.isArray(spec.items)) {
      spec.items.forEach((item, i) => this.#checkUnchanged(item, actual?.[i], baseline?.[i], `${path}[${i}]`));
    } else if (plain(spec.items)) {
      for (const [key, item] of Object.entries(spec.items)) {
        this.#checkUnchanged(item, actual?.[key], baseline?.[key], `${path}.${key}`);
      }
    } else {
      for (const [key, item] of Object.entries(spec)) {
        if (!key.startsWith('$')) this.#checkUnchanged(item, actual?.[key], baseline?.[key], `${path}.${key}`);
      }
    }
  }

  #apply(spec, target, refs, path) {
    if (spec?.$unchanged) return;
    if (!isObject(spec) || !isObject(target)) return;
    const id = spec.$new ?? spec.$ref;
    if (id && refs.has(id) && refs.get(id) !== target) failure(path, 'post-state receiver changed identity');
    if (Array.isArray(target) && Array.isArray(spec.items)) {
      target.splice(0, target.length, ...spec.items.map((v, i) => this.#materialize(v, refs, `${path}[${i}]`)));
    } else if (spec.$type === 'builtins.dict' || own(spec, 'keys') || (plain(spec.items) && !Array.isArray(spec.items))) {
      if (spec.keys) {
        for (const k of Object.keys(target)) if (!spec.keys.includes(k)) delete target[k];
      }
      for (const [k, v] of Object.entries(spec.items || {})) {
        if (isObject(target[k]) && (v?.$ref || v?.$unchanged)) this.#apply(v, target[k], refs, `${path}.${k}`);
        else target[k] = this.#materialize(v, refs, `${path}.${k}`);
      }
    } else {
      for (const [k, v] of Object.entries(spec)) {
        if (k.startsWith('$')) continue;
        if (isObject(target[k]) && (v?.$ref || v?.$unchanged)) this.#apply(v, target[k], refs, `${path}.${k}`);
        else target[k] = this.#materialize(v, refs, `${path}.${k}`);
      }
    }
  }

  #materialize(spec, refs, path) {
    if (!isObject(spec)) return spec;
    if (spec.$ref) {
      if (!refs.has(spec.$ref)) failure(path, `unknown reference ${spec.$ref}`);
      return refs.get(spec.$ref);
    }
    if (Array.isArray(spec)) return spec.map((v, i) => this.#materialize(v, refs, `${path}[${i}]`));
    if (spec.$new) {
      if (refs.has(spec.$new)) failure(path, `duplicate $new ${spec.$new}`);
      const out = spec.$type === 'builtins.list' ? [] : spec.$type === 'builtins.dict' ? {} :
        this.types[spec.$type] ? Object.create(this.types[spec.$type].prototype) : {};
      refs.set(spec.$new, out);
      this.#apply(spec, out, refs, path);
      return out;
    }
    const out = {};
    for (const [k, v] of Object.entries(spec)) out[k] = this.#materialize(v, refs, `${path}.${k}`);
    return out;
  }

  replay(receiver, name, args = [], kwargs = {}) {
    const { entry, refs } = this.#expect(receiver, name, args, kwargs);
    if (receiver !== Free) this.#apply(entry.after.obj, receiver, refs, 'after.obj');
    args.forEach((arg, i) => this.#apply(entry.after.args[i], arg, refs, `after.args[${i}]`));
    for (const [k, v] of Object.entries(kwargs)) this.#apply(entry.after.kwargs[k], v, refs, `after.kwargs.${k}`);
    let value;
    if (own(entry.result, 'return')) value = this.#materialize(entry.result.return, refs, 'result.return');
    this.references = refs;
    this.cursor++;
    if (this.stream) this.stream.advance();
    if (own(entry.result, 'raise')) {
      const spec = entry.result.raise;
      const ErrorType = { Error, TypeError, RangeError, SyntaxError, ReferenceError }[spec.$type] || Error;
      throw new ErrorType(...(spec.args || []));
    }
    return value;
  }

  async test(invoke, receiver, name, args = [], kwargs = {}) {
    if (typeof invoke !== 'function') failure('test', 'expected function');
    const { entry, refs } = this.#expect(receiver, name, args, kwargs);
    const baseline = structuredClone({
      receiver: receiver === Free ? null : receiver,
      args,
      kwargs
    });
    let value, thrown;
    try { value = await invoke(...args, ...(Object.keys(kwargs).length ? [kwargs] : [])); } catch (e) { thrown = e; }
    if (receiver !== Free) this.#checkUnchanged(entry.after.obj, receiver, baseline.receiver, 'after.obj');
    args.forEach((arg, i) => this.#checkUnchanged(entry.after.args[i], arg, baseline.args[i], `after.args[${i}]`));
    for (const [key, value] of Object.entries(kwargs)) {
      this.#checkUnchanged(entry.after.kwargs[key], value, baseline.kwargs[key], `after.kwargs.${key}`);
    }
    if (receiver !== Free) this.#compare(entry.after.obj, receiver, refs, 'after.obj');
    args.forEach((arg, i) => this.#compare(entry.after.args[i], arg, refs, `after.args[${i}]`));
    for (const [k, v] of Object.entries(kwargs)) this.#compare(entry.after.kwargs[k], v, refs, `after.kwargs.${k}`);
    if (own(entry.result, 'raise')) {
      const expected = entry.result.raise;
      if (!thrown || thrown.constructor.name !== expected.$type ||
          thrown.message !== expected.args?.[0]) failure('result.raise', 'exception mismatch');
    } else {
      if (thrown) failure('result.return', `unexpected exception ${thrown.constructor.name}`);
      this.#compare(entry.result.return, value, refs, 'result.return');
    }
    this.references = refs;
    this.cursor++;
    if (thrown) throw thrown;
    return value;
  }
}

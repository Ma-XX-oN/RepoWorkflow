/** Frozen #518/#553 grammar: recording-wide identity and bounded JSONL input. */
import { openSync, readSync, closeSync } from 'node:fs';

export function identityEntry(entry, identities, index) {
  const walk = (value, path) => {
    if (Array.isArray(value)) {
      value.forEach((v, i) => walk(v, `${path}[${i}]`));
      return;
    }
    if (!value || typeof value !== 'object') return;
    if (Object.hasOwn(value, '$new')) {
      if (identities.has(value.$new)) throw new Error(`${path}: duplicate $new ${value.$new}`);
      identities.add(value.$new);
    } else if (Object.hasOwn(value, '$ref') && !identities.has(value.$ref)) {
      throw new Error(`${path}: unknown or forward $ref ${value.$ref}`);
    }
    for (const [key, v] of Object.entries(value)) {
      if (key !== '$new' && key !== '$ref') walk(v, `${path}.${key}`);
    }
  };
  walk(entry.call, `interaction[${index}].call`);
  walk(entry.before, `interaction[${index}].before`);
  walk(entry.after, `interaction[${index}].after`);
  walk(entry.result, `interaction[${index}].result`);
}

export function identityRecording(entries) {
  const identities = new Set();
  entries.forEach((entry, i) => identityEntry(entry, identities, i));
}

// Each iterator retains one line only.  The independent scan validates
// the entire file before the first executable replay call.
export class JsonlReader {
  constructor(path, validate, maxLine = 1048576) {
    this.path = path;
    this.validate = validate;
    this.maxLine = maxLine;
    this.fd = null;
    this.reset();
  }
  reset() {
    this.close();
    this.fd = openSync(this.path, 'r');
    this.offset = 0;
    this.bytes = Buffer.alloc(0);
    this.eof = false;
    this.index = 0;
    this.current = undefined;
    try { this.advance(); } catch (e) { this.close(); throw e; }
  }
  close() {
    if (this.fd !== null) closeSync(this.fd);
    this.fd = null;
  }
  nextLine() {
    while (true) {
      const newline = this.bytes.indexOf(10);
      if (newline >= 0) {
        const line = this.bytes.subarray(0, newline);
        this.bytes = Buffer.from(this.bytes.subarray(newline + 1));
        return line.toString('utf8').replace(/\r$/, '');
      }
      if (this.eof) {
        if (!this.bytes.length) return null;
        const line = this.bytes.toString('utf8');
        this.bytes = Buffer.alloc(0);
        return line;
      }
      if (this.bytes.length > this.maxLine) throw new Error('JSONL line exceeds bounded maximum');
      const chunk = Buffer.allocUnsafe(16384);
      const n = readSync(this.fd, chunk, 0, chunk.length, this.offset);
      if (!n) this.eof = true;
      else {
        this.offset += n;
        this.bytes = Buffer.concat([this.bytes, chunk.subarray(0, n)]);
        if (this.bytes.length > this.maxLine + 16384) {
          throw new Error('JSONL line exceeds bounded maximum');
        }
      }
    }
  }
  advance() {
    let line;
    do { line = this.nextLine(); } while (line !== null && !line.trim());
    if (line === null) {
      this.current = undefined;
      this.close();
      return;
    }
    if (Buffer.byteLength(line) > this.maxLine) throw new Error('JSONL line exceeds bounded maximum');
    let entry;
    try { entry = JSON.parse(line); }
    catch (e) { throw new Error(`interaction[${this.index}]: malformed/truncated JSONL: ${e.message}`); }
    this.validate(entry, this.index);
    this.current = entry;
    this.index++;
  }
  peek() { return this.current; }
  *records() {
    const reader = new JsonlReader(this.path, this.validate, this.maxLine);
    try {
      while (reader.peek() !== undefined) {
        yield reader.peek();
        reader.advance();
      }
    } finally { reader.close(); }
  }
}

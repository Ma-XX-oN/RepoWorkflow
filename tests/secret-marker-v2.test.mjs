import assert from 'node:assert/strict';
import { createHash, createHmac } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import {
  FORMAT, FORMAT_V2, SecretMarkerDecoder, decodeText, parseMarker,
  measureLogicalLength, validateScopeMetadata
} from '../scripts/secret-marker-decoder.mjs';

const fixtures = JSON.parse(readFileSync(new URL(
  './fixtures/redaction-marker-v2.json', import.meta.url), 'utf8'));
const v1 = JSON.parse(readFileSync(new URL(
  './fixtures/redaction-marker-v1.json', import.meta.url), 'utf8'));
const [old, rotated] = fixtures.generations;
const scope = generation => ({
  redaction_format: FORMAT_V2,
  redaction_scope: generation.scope,
  redaction_key_generation: generation.scope,
  redaction_key_epoch: generation.epoch,
  redaction_key_storage: 'tampermonkey-script-installation'
});
const oldMeta = scope(old);
const rotatedMeta = scope(rotated);
const legacyMeta = {
  redaction_format: FORMAT, redaction_scope: v1.test_scope
};

// The producer HMAC key here is PUBLIC SYNTHETIC fixture material. No decoder
// is ever given a key. CHECK is deliberately unkeyed and not authentication.
function independentMarker(vector, publicTestKey) {
  const value = Buffer.from(vector.original, 'utf8');
  const length = Buffer.alloc(4);
  length.writeUInt32BE(value.length);
  const id = createHmac('sha256', Buffer.from(publicTestKey, 'hex'))
    .update(Buffer.concat([
      Buffer.from('DC-SECRET-ID-V1\0'), length, value
    ])).digest('hex').slice(0, 48);
  const body = vector.type + '/' + id +
    (vector.params === null ? '' : '/' + vector.params);
  const check = createHash('sha256').update(Buffer.concat([
    Buffer.from('DC-SECRET-MARKER-V1\0'), Buffer.from(body, 'ascii')
  ])).digest('hex').slice(0, 32);
  return { id, check, marker: '[' + check + '/' + body + ']' };
}

test('frozen V1 and DC #312 V2 golden vectors: six types, both generations', () => {
  assert.equal(fixtures.format, FORMAT_V2);
  assert.equal(fixtures.synthetic_only, true);
  assert.equal(fixtures.public_test_keys_only, true);
  for (const [index, generation] of fixtures.generations.entries()) {
    const metadata = scope(generation);
    for (const vector of v1.vectors) {
      const expected = index === 0 ? vector :
        fixtures.rotated_vectors.find(x => x.type === vector.type);
      assert.ok(expected);
      const actual = independentMarker(vector, generation.key_hex);
      assert.equal(actual.id, expected.id);
      assert.equal(actual.check, expected.check);
      assert.deepEqual(parseMarker(actual.marker), {
        type: vector.type, id: expected.id,
        params: vector.params === null ? undefined : vector.params
      });
      assert.deepEqual(measureLogicalLength(decodeText(actual.marker, metadata)),
        [vector.utf8_bytes, vector.utf16_units]);
    }
  }
  const unicode = independentMarker(v1.vectors.find(v => v.type === 'O'),
    old.key_hex);
  assert.equal(unicode.id, old.id);
  assert.equal(unicode.check, old.check);
});

test('V2 stable synthetic values across tabs, reload, and conversations', () => {
  const a = independentMarker(v1.vectors[0], old.key_hex).marker;
  const b = independentMarker(v1.vectors[1], old.key_hex).marker;
  const tabA = new SecretMarkerDecoder(oldMeta);
  const tabB = new SecretMarkerDecoder({ ...oldMeta });
  const one = tabA.decodeMarker(a);
  tabA.decodeMarker(b);
  tabB.decodeMarker(b);
  assert.equal(tabB.decodeMarker(a), one);
  assert.equal(new SecretMarkerDecoder(oldMeta).decodeMarker(a), one);
  assert.equal(decodeText(a + a, oldMeta), one + one);
  assert.equal(decodeText(a, oldMeta), one);
});

test('V2 A to B to A replay and out-of-order chunks respect generation', () => {
  const vector = v1.vectors.find(v => v.type === 'O');
  const before = independentMarker(vector, old.key_hex).marker;
  const after = independentMarker(vector, rotated.key_hex).marker;
  const expectedA = decodeText(before, oldMeta);
  const expectedB = decodeText(after, rotatedMeta);
  const timeline = [
    [before, oldMeta, expectedA], [after, rotatedMeta, expectedB],
    [before, oldMeta, expectedA]
  ];
  for (const [marker, metadata, expected] of timeline) {
    assert.equal(decodeText(marker, metadata), expected);
  }
  const reversed = [...timeline].reverse();
  for (const [marker, metadata, expected] of reversed) {
    assert.equal(decodeText(marker, metadata), expected);
  }
  // Equalities BETWEEN generations are unknown; no such assertion is made.
  assert.equal(new SecretMarkerDecoder(oldMeta).scope, old.scope);
  assert.equal(new SecretMarkerDecoder(rotatedMeta).scope, rotated.scope);
  assert.equal(new SecretMarkerDecoder(oldMeta).format, FORMAT_V2);
});

test('V1 remains ephemeral and legacy placeholder remains opaque', () => {
  const m = v1.vectors[0].marker;
  assert.equal(decodeText(m, legacyMeta),
    new SecretMarkerDecoder(legacyMeta).decodeMarker(m));
  assert.equal(decodeText('[redacted]', oldMeta), '[redacted]');
  assert.equal(decodeText('[redacted]', legacyMeta), '[redacted]');
  // V1 grammar is valid inside a V2 segment; the segment sets the namespace.
  assert.deepEqual(measureLogicalLength(decodeText(m, oldMeta)), [36, 36]);
  const decoder = new SecretMarkerDecoder(oldMeta);
  assert.equal('key' in decoder, false);
  assert.equal('hmacKey' in decoder, false);
});

test('V2 context-agnostic decoder preserves JSON SSE WS XHR HTTP framing', () => {
  const a = independentMarker(v1.vectors[0], old.key_hex).marker;
  const b = independentMarker(v1.vectors[1], old.key_hex).marker;
  const request = 'GET /?credential=' + a + ' HTTP/1.1\r\nX-Test: ' + b + '\r\n';
  const json = JSON.stringify({ credential: a, item: b, literal: '[redacted]' });
  const sse = 'event: message\ndata: ' + json + '\n\n';
  const ws = JSON.stringify({ event: 'ws', credential: b });
  const xhr = JSON.stringify({ responseText: a });
  for (const text of [request, json, sse, ws, xhr]) {
    const decoded = decodeText(text, oldMeta);
    assert.equal(decoded.includes(a), false);
    assert.equal(decoded.includes(b), false);
    assert.equal(decoded.length > 0, true);
  }
  assert.equal(JSON.parse(decodeText(json, oldMeta)).literal, '[redacted]');
  assert.ok(decodeText(sse, oldMeta).startsWith('event: message\ndata: {'));
  assert.ok(decodeText(sse, oldMeta).endsWith('\n\n'));
  assert.equal(JSON.parse(decodeText(ws, oldMeta)).event, 'ws');
  assert.ok(decodeText(request, oldMeta).endsWith('\r\n'));
});

test('stream splits preserve Unicode O width and bounded candidate handling', () => {
  const marker = independentMarker(v1.vectors.find(v => v.type === 'O'),
    rotated.key_hex).marker;
  const input = 'start 😀\n' + marker + '\n[literal] end';
  const baseline = decodeText(input, rotatedMeta);
  assert.ok(baseline.includes('[literal]'));
  for (let i = 1; i < input.length; i++) {
    const decoder = new SecretMarkerDecoder(rotatedMeta);
    assert.equal(decoder.feed(input.slice(0, i)) +
      decoder.feed(input.slice(i), true), baseline);
  }
  const unicode = decodeText(marker, rotatedMeta);
  assert.deepEqual(measureLogicalLength(unicode), [10, 5]);
  const incomplete = new SecretMarkerDecoder(rotatedMeta);
  incomplete.feed(marker.slice(0, -1));
  assert.throws(() => incomplete.finish(), /TRUNCATED_MARKER/);
});

test('V2 metadata validation fails closed on absent, corrupt and mixed fields', () => {
  assert.deepEqual(validateScopeMetadata(oldMeta), {
    format: FORMAT_V2, scope: old.scope,
    generation: old.scope, epoch: old.epoch
  });
  for (const name of Object.keys(oldMeta)) {
    const missing = { ...oldMeta };
    delete missing[name];
    assert.throws(() => new SecretMarkerDecoder(missing), name);
  }
  const changed = (name, value) => ({ ...oldMeta, [name]: value });
  for (const value of [0, -1, 1.5, '1', null, NaN,
                       Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => new SecretMarkerDecoder(
      changed('redaction_key_epoch', value)), /EPOCH/);
  }
  assert.throws(() => new SecretMarkerDecoder(changed(
    'redaction_key_generation', rotated.scope)), /MISMATCH/);
  assert.throws(() => new SecretMarkerDecoder(changed(
    'redaction_key_generation', old.scope.toUpperCase())), /GENERATION/);
  assert.throws(() => new SecretMarkerDecoder(changed(
    'redaction_scope', old.scope.toUpperCase())), /SCOPE/);
  assert.throws(() => new SecretMarkerDecoder(changed(
    'redaction_key_storage', 'web-locks-only')), /STORAGE/);
  assert.throws(() => new SecretMarkerDecoder(changed(
    'redaction_format', 'dc-secret-marker/3')), /FORMAT/);
  assert.throws(() => new SecretMarkerDecoder(changed(
    'redaction_format', FORMAT)), /MIXED/);
  assert.throws(() => new SecretMarkerDecoder({ ...legacyMeta,
    redaction_key_epoch: 1 }), /MIXED/);
  assert.throws(() => new SecretMarkerDecoder(null), /METADATA/);
  assert.throws(() => new SecretMarkerDecoder([]), /METADATA/);
});

test('invalid checks fail; publicly forgeable CHECK is not authenticity', () => {
  const valid = independentMarker(v1.vectors[0], old.key_hex).marker;
  const tampered = '[f' + valid.slice(2);
  assert.throws(() => decodeText(tampered, oldMeta), /INVALID_MARKER_CHECK/);
  const forged = independentMarker({ type: 'H', params: '2',
    original: 'aa' }, rotated.key_hex).marker;
  // Anyone can construct this checksum. Valid CHECK does not prove origin.
  assert.equal(parseMarker(forged).type, 'H');
  assert.equal(measureLogicalLength(decodeText(forged, rotatedMeta))[0], 2);
  assert.throws(() => decodeText(forged, changedScopeWithWrongEpoch()),
    /INVALID_REDACTION_EPOCH/);
  function changedScopeWithWrongEpoch() {
    return { ...rotatedMeta, redaction_key_epoch: 0 };
  }
});

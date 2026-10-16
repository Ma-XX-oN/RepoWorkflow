import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import {
  SecretMarkerDecoder, parseMarker, decodeText, measureLogicalLength
} from '../scripts/secret-marker-decoder.mjs';

const metadata = {
  redaction_format: 'dc-secret-marker/1',
  redaction_scope: '00112233445566778899aabbccddeeff'
};
const vectors = [
  ['U', null, 36, 36],
  ['P', null, 36, 36],
  ['H', '12', 12, 12],
  ['B', '6', 6, 6],
  ['J', '19,15,4', 40, 40],
  ['O', '1234', 10, 5]
];
function marker(type, params, id = 'a'.repeat(48)) {
  const body = type + '/' + id + (params === null ? '' : '/' + params);
  const check = createHash('sha256').update(
    Buffer.concat([Buffer.from('DC-SECRET-MARKER-V1\0'), Buffer.from(body)])
  ).digest('hex').slice(0, 32);
  return '[' + check + '/' + body + ']';
}
test('golden-compatible type widths and arbitrary marker two-way splits', () => {
  for (const [type, params, utf8, utf16] of vectors) {
    const value = marker(type, params);
    assert.equal(parseMarker(value).type, type);
    const expected = decodeText(value, metadata);
    assert.deepEqual(measureLogicalLength(expected), [utf8, utf16]);
    for (let i = 1; i < value.length; i++) {
      const stream = new SecretMarkerDecoder(metadata);
      assert.equal(stream.feed(value.slice(0, i)) +
        stream.feed(value.slice(i), true), expected);
    }
  }
});
test('same tuple deterministic across ordering and new instances', () => {
  const a = marker('U', null, 'a'.repeat(48));
  const b = marker('U', null, 'b'.repeat(48));
  const one = new SecretMarkerDecoder(metadata);
  const two = new SecretMarkerDecoder(metadata);
  const first = one.decodeMarker(a);
  one.decodeMarker(b);
  two.decodeMarker(b);
  assert.equal(first, two.decodeMarker(a));
  assert.equal(one.decodeMarker(a), first);
});
test('scope changes get independent cache and replacements', () => {
  const m = marker('P', null);
  const alt = { ...metadata, redaction_scope: 'ffeeddccbbaa99887766554433221100' };
  assert.notEqual(decodeText(m, metadata), decodeText(m, alt));
});
test('literal brackets, concatenated markers, JSON and SSE remain valid', () => {
  const m = marker('U', null);
  const text = 'one [[ literal [ok] two ' + m + ' and ' + m;
  const out = decodeText(text, metadata);
  assert.equal((out.match(/550e/g) ?? []).length, 0);
  assert.ok(out.includes('[[ literal [ok]'));
  const payload = JSON.stringify({ value: m, ordinary: '[ok]' });
  const decoded = decodeText(payload, metadata);
  assert.equal(JSON.parse(decoded).ordinary, '[ok]');
  const sse = decodeText('data: ' + payload + '\n\n', metadata);
  assert.ok(sse.startsWith('data: '));
  assert.ok(sse.endsWith('\n\n'));
});
test('invalid scope, version, checksum, type and shape fail closed', () => {
  assert.throws(() => new SecretMarkerDecoder({ ...metadata, redaction_scope: null }));
  assert.throws(() => new SecretMarkerDecoder({ ...metadata, redaction_format: 'dc-secret-marker/2' }));
  const m = marker('U', null);
  assert.throws(() => parseMarker('[0' + m.slice(2)));
  assert.throws(() => decodeText('[0' + m.slice(2), metadata));
  assert.throws(() => parseMarker(marker('Z', null)));
  assert.throws(() => parseMarker(marker('H', '012')));
  assert.throws(() => decodeText(m.slice(0, -1), metadata));
});
test('legacy redacted placeholders unchanged and no secret HMAC key available', () => {
  assert.equal(decodeText('[redacted]', metadata), '[redacted]');
  assert.equal('key' in new SecretMarkerDecoder(metadata), false);
});

test('pinned DC #300 golden vectors validate without original HMAC key', async () => {
  const { readFileSync } = await import('node:fs');
  const { fileURLToPath } = await import('node:url');
  const path = fileURLToPath(new URL('./fixtures/redaction-marker-v1.json', import.meta.url));
  const fixture = JSON.parse(readFileSync(path, 'utf8'));
  assert.equal(fixture.format, 'dc-secret-marker/1');
  assert.equal(fixture.fixture_version, 1);
  assert.equal(fixture.synthetic_only, true);
  const scope = { ...metadata, redaction_scope: fixture.test_scope };
  for (const vector of fixture.vectors) {
    const parsed = parseMarker(vector.marker);
    assert.equal(parsed.type, vector.type);
    assert.equal(parsed.id, vector.id);
    assert.equal(parsed.params ?? null, vector.params);
    const value = decodeText(vector.marker, scope);
    assert.deepEqual(measureLogicalLength(value),
      [vector.utf8_bytes, vector.utf16_units]);
    assert.equal(decodeText(vector.marker, scope), value);
  }
});

test('classified registry rejects overlap and unsupported free-text context', async () => {
  const { TYPE_REGISTRY, identifyTypes } = await import('../scripts/secret-marker-decoder.mjs');
  assert.equal(TYPE_REGISTRY.U.contexts['json.string'], true);
  assert.deepEqual(identifyTypes('550e8400-e29b-41d4-a716-446655440000', 'json.string'), ['U']);
  assert.throws(() => identifyTypes('deadbeefcafe', 'json.string', ['H','B']), /AMBIGUOUS_SECRET_TYPE/);
  assert.deepEqual(identifyTypes('deadbeefcafe', 'text.plain'), []);
  assert.equal(TYPE_REGISTRY.O.identify('Aé界𐐀', 'json.string'), false);
});
test('truncated reserved markers and excessive candidates fail closed', () => {
  const m = marker('J', '19,15,4');
  const decoder = new SecretMarkerDecoder(metadata);
  assert.equal(decoder.feed(m.slice(0, 40)), '');
  assert.throws(() => decoder.finish(), /TRUNCATED_MARKER/);
  const long = '[' + 'a'.repeat(32) + '/U/' + 'a'.repeat(400);
  assert.throws(() => decodeText(long, metadata), /MARKER_TOO_LONG/);
});

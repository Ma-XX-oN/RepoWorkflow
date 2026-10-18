import assert from 'node:assert/strict';
import { createHash, createHmac, webcrypto } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';
import { decodeText, measureLogicalLength, parseMarker } from
  '../scripts/secret-marker-decoder.mjs';

// WIP #313 producer source is independently pinned. This proves only a
// source-executed synthetic interface, NOT authenticated browser certification.
const sourcePath = process.env.DC313_SERVICE_PATH;
assert.ok(sourcePath, 'DC313_SERVICE_PATH_REQUIRED');
const sourceBytes = readFileSync(sourcePath);
const gitBlobHash = createHash('sha1')
  .update(Buffer.from('blob ' + sourceBytes.length + '\0'))
  .update(sourceBytes).digest('hex');
assert.equal(gitBlobHash, 'c9e3f7bbf9c96fe101cb04764f398b5fecf50276',
  'DC313_PINNED_SOURCE_BLOB_MISMATCH');
const { create, createAuthority } = vm.runInNewContext(
  sourceBytes.toString('utf8') + '\n({ create: communicationPersistentHmacService,' +
  ' createAuthority: communicationPersistentHmacChatgptAuthority });',
  { Uint8Array, Array, Map, Set, Object, Number, Error, JSON });

function makeFixture() {
  let current = null;
  let gate = Promise.resolve();
  const navigator = {
    locks: {
      async request(name, options, callback) {
        assert.equal(name, 'downloadconversation:secret-marker-key-v2:all-tabs');
        assert.equal(options.mode, 'exclusive');
        const previous = gate;
        let release;
        gate = new Promise(resolve => { release = resolve; });
        await previous;
        try { return await callback({ mode: 'exclusive' }); }
        finally { release(); }
      }
    }
  };
  const origin = { origin: 'https://chatgpt.com' };
  const authority = createAuthority(navigator, origin);
  assert.equal(authority.capability, 'linearizable-chatgpt-web-lock-fenced-v1');
  const storage = {
    async get(_name, fallback) {
      return current === null ? fallback : structuredClone(current);
    },
    async set(_name, next) {
      current = structuredClone(next);
    }
  };
  const dependencies = { authority, storage, crypto: webcrypto };
  return {
    open: () => create(dependencies),
    record: () => structuredClone(current),
    dependencies, navigator, origin
  };
}

function workerKey(service, token) {
  let bytes;
  service.provision(token, {
    postMessage(message, transfer) {
      assert.equal(message.type, 'dc-hmac-key-v2');
      assert.equal(message.token, token);
      assert.equal(message.key_bytes.length, 32);
      assert.equal(transfer.length, 1);
      bytes = Buffer.from(message.key_bytes);
    }
  });
  return bytes;
}

function encodeSynthetic(key, secret) {
  const input = Buffer.from(secret, 'utf8');
  const length = Buffer.alloc(4);
  length.writeUInt32BE(input.length);
  const id = createHmac('sha256', key).update(Buffer.concat([
    Buffer.from('DC-SECRET-ID-V1\0'), length, input
  ])).digest('hex').slice(0, 48);
  const body = 'O/' + id + '/1234';
  const check = createHash('sha256').update(Buffer.concat([
    Buffer.from('DC-SECRET-MARKER-V1\0'),
    Buffer.from(body, 'ascii')
  ])).digest('hex').slice(0, 32);
  return '[' + check + '/' + body + ']';
}

test('exact #313 service metadata and provisioned synthetic HMAC interoperate with #691', async () => {
  const fixture = makeFixture();
  const tabA = fixture.open();
  const tabB = fixture.open();
  const [a, b] = await Promise.all([tabA.admit(), tabB.admit()]);
  const oldA = workerKey(tabA, a.token);
  const oldB = workerKey(tabB, b.token);
  const markerA = encodeSynthetic(oldA, 'Aé界𐐀');
  const markerB = encodeSynthetic(oldB, 'Aé界𐐀');
  assert.equal(markerA, markerB);
  assert.equal(parseMarker(markerA).type, 'O');
  assert.equal(a.metadata.redaction_format, 'dc-secret-marker/2');
  assert.equal(a.metadata.redaction_scope, b.metadata.redaction_scope);
  assert.deepEqual(JSON.parse(JSON.stringify(a.metadata)),
    JSON.parse(JSON.stringify(b.metadata)));
  const replayA = decodeText(markerA, a.metadata);
  assert.equal(decodeText(markerB, b.metadata), replayA);
  assert.deepEqual(measureLogicalLength(replayA), [10, 5]);
  assert.equal(JSON.stringify(a.metadata).includes(
    fixture.record().key_hex), false);
  assert.equal(fixture.record().epoch, 1);

  const rotator = fixture.open();
  const drain = await rotator.randomize(true);
  assert.equal(drain.state, 'DRAINING');
  await assert.rejects(() => fixture.open().admit(),
    /rotation-draining/);
  await tabA.complete(a.token);
  await tabB.complete(b.token);
  const nextService = fixture.open();
  const next = await nextService.admit();
  assert.equal(next.metadata.redaction_key_epoch, 2);
  assert.notEqual(next.metadata.redaction_scope, a.metadata.redaction_scope);
  const nextTab = fixture.open();
  const generation = await nextTab.admit();
  const newMarker = encodeSynthetic(workerKey(nextTab, generation.token),
    'Aé界𐐀');
  assert.equal(next.metadata.redaction_scope,
    generation.metadata.redaction_scope);
  assert.equal(newMarker, encodeSynthetic(
    workerKey(nextService, next.token), 'Aé界𐐀'));
  assert.equal(decodeText(newMarker, generation.metadata),
    decodeText(newMarker, next.metadata));
  // Different generations give no cross-generation original-secret inference.
  await nextTab.complete(generation.token);
  await nextService.complete(next.token);
  assert.equal(fixture.record().pending.length, 0);
  assert.equal(decodeText(markerA, a.metadata), replayA);
});

test('exact #313 source rejects unverified authority without leaking key', async () => {
  const fixture = makeFixture();
  const service = create({ ...fixture.dependencies, authority: null });
  await assert.rejects(() => service.admit(),
    /shared-authority-unavailable/);
  assert.equal(fixture.record(), null);
});

test('actual same-origin Web Locks adapter rejects unsupported origins and failed fences', async () => {
  const fixture = makeFixture();
  assert.equal(createAuthority(fixture.navigator,
    { origin: 'https://chat.openai.com' }), null);
  assert.equal(createAuthority(fixture.navigator,
    { origin: 'http://chatgpt.com' }), null);
  assert.equal(createAuthority({}, fixture.origin), null);
  const maliciousNavigator = { locks: {
    async request(_name, _options, callback) {
      return callback({ mode: 'shared' });
    }
  } };
  const authority = createAuthority(maliciousNavigator, fixture.origin);
  const service = create({ ...fixture.dependencies, authority });
  await assert.rejects(() => service.admit(), /web-lock-not-acquired/);
  assert.equal(fixture.record(), null);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { InterfacePlayback, Free } from '../testing/javascript/interface-playback.mjs';
const id = value => value;

async function captured(method, receiver, name, args) {
  const engine = new InterfacePlayback();
  const result = await engine.record(id, method, receiver, name, args);
  const dir = await mkdtemp(join(tmpdir(), 'rwf670-'));
  const file = join(dir, 'test.jsonl');
  await engine.save(file);
  const check = new InterfacePlayback();
  await check.load(file);
  assert.equal(check.entries.length, 1);
  return { engine, check, result, file };
}

test('free function scalar result, save/load/replay and actual comparison', async () => {
  const { check } = await captured((a, b) => a + b, Free, 'add', [3, 7]);
  assert.equal(check.replay(Free, 'add', [3, 7]), 10);
  assert.throws(() => check.replay(Free, 'add', [3, 7]), /exhausted/);
  check.reset();
  assert.equal(await check.test((a, b) => a + b, Free, 'add', [3, 7]), 10);
});

test('method consequential mutation replay', async () => {
  const obj = { pos: 2, nested: { flag: 'a' } };
  const { check } = await captured(() => { obj.pos = 5; obj.nested.flag = 'b'; return true; }, obj, 'advance', []);
  const replica = { pos: 2, nested: { flag: 'a' } };
  assert.equal(check.replay(replica, 'advance'), true);
  assert.deepEqual(replica, { pos: 5, nested: { flag: 'b' } });
});

test('member compare test verifies post-state', async () => {
  const obj = { pos: 0 };
  const { check } = await captured(() => ++obj.pos, obj, 'increment', []);
  const clone = { pos: 0 };
  assert.equal(await check.test(() => ++clone.pos, clone, 'increment'), 1);
  check.reset();
  const changed = { pos: 0 };
  await assert.rejects(check.test(() => { changed.pos += 2; return 2; }, changed, 'increment'), /after.obj/);
  assert.equal(check.cursor, 0);
});

test('exception recorded, replayed and actual exception verified', async () => {
  const { check } = await (async () => {
    const p = new InterfacePlayback();
    await assert.rejects(p.record(id, () => { throw new TypeError('bad input'); }, Free, 'parse'), /bad input/);
    const c = new InterfacePlayback(); await c.load(p.entries); return { check: c };
  })();
  assert.throws(() => check.replay(Free, 'parse'), { name: 'TypeError', message: 'bad input' });
  check.reset();
  await assert.rejects(check.test(() => { throw new TypeError('bad input'); }, Free, 'parse'), /bad input/);
  assert.equal(check.cursor, 1);
});

test('wrong call is rejected without consumption', async () => {
  const { check } = await captured(() => 'yes', Free, 'name', []);
  assert.throws(() => check.replay(Free, 'other'), /expected name/);
  assert.equal(check.cursor, 0);
});

test('object equality does not replace identity', async () => {
  const shared = { value: 2 };
  const p = new InterfacePlayback();
  await p.record(id, a => a, Free, 'alias', [shared, shared]);
  const c = new InterfacePlayback(); await c.load(p.entries);
  assert.throws(() => c.replay(Free, 'alias', [{ value: 2 }, { value: 2 }]), /identity mismatch/);
  c.reset();
  const another = { value: 2 };
  assert.equal(c.replay(Free, 'alias', [another, another]), another);
});

test('malformed unknown reserved metadata rejected', async () => {
  const p = new InterfacePlayback();
  await assert.rejects(p.load([{ call: { fn_name: 'x', obj: { $free: true } },
    before: { args: [], kwargs: {} }, after: { args: [], kwargs: {} }, result: { return: { $oops: 1 } } }]), /unknown reserved key/);
});

test('truncated JSONL rejected', async () => {
  const p = new InterfacePlayback();
  const dir = await mkdtemp(join(tmpdir(), 'rwf670-'));
  const file = join(dir, 'bad.jsonl');
  const { writeFile } = await import('node:fs/promises');
  await writeFile(file, '{"call":');
  await assert.rejects(p.load(file), /Unexpected end|JSON/);
});

test('filtered irrelevant state does not affect replay', async () => {
  const obj = { status: 'new', private: 'untouched' };
  const p = new InterfacePlayback();
  await p.record(entry => {
    delete entry.before.obj.items.private;
    delete entry.after.obj.items.private;
    delete entry.before.obj.keys;
    delete entry.after.obj.keys;
    return entry;
  }, () => { obj.status = 'done'; return 42; }, obj, 'finish');
  const c = new InterfacePlayback(); await c.load(p.entries);
  const replica = { status: 'new', private: 'different' };
  assert.equal(c.replay(replica, 'finish'), 42);
  assert.equal(replica.private, 'different');
  assert.equal(replica.status, 'done');
});

test('consecutive method interactions retain one logical receiver', async () => {
  const object = { n: 0 };
  const p = new InterfacePlayback();
  await p.record(id, () => ++object.n, object, 'step');
  await p.record(id, () => ++object.n, object, 'step');
  const q = new InterfacePlayback(); await q.load(p.entries);
  const target = { n: 0 };
  assert.equal(q.replay(target, 'step'), 1);
  assert.equal(q.replay(target, 'step'), 2);
  assert.equal(target.n, 2);
});

test('keyword argument object identity and state is preserved', async () => {
  const state = { ready: false };
  const p = new InterfacePlayback();
  await p.record(id, kwargs => { kwargs.state.ready = true; return 'ok'; },
    Free, 'configure', [], { state });
  const q = new InterfacePlayback(); await q.load(p.entries);
  const obj = { ready: false };
  assert.equal(q.replay(Free, 'configure', [], { state: obj }), 'ok');
  assert.equal(obj.ready, true);
});

test('selective Unchanged selector passes without mutating', async () => {
  const p = new InterfacePlayback();
  await p.load([{ call: { fn_name: 'stay', obj: { $free: true } },
    before: { args: [{ $new: 'd', $type: 'builtins.dict', keys: ['mode', 'extra'], items: { mode: 'a', extra: 3 } }], kwargs: {} },
    after: { args: [{ $unchanged: { keys: ['mode'] } }], kwargs: {} }, result: { return: true } }]);
  const original = { mode: 'a', extra: 3 };
  assert.equal(p.replay(Free, 'stay', [original]), true);
  assert.deepEqual(original, { mode: 'a', extra: 3 });
});

test('extra unsupported arbitrary objects are not silently serialized', async () => {
  const p = new InterfacePlayback();
  await assert.rejects(p.record(id, () => new Map([['a', 1]]), Free, 'getMap'), /unsupported|map|object/i);
});

test('filtered real exception mismatch rejects and does not consume', async () => {
  const p = new InterfacePlayback();
  await assert.rejects(p.record(id, () => { throw new RangeError('wrong'); }, Free, 'danger'), /wrong/);
  const q = new InterfacePlayback(); await q.load(p.entries);
  await assert.rejects(q.test(() => { throw new TypeError('wrong'); }, Free, 'danger'), /exception mismatch/);
  assert.equal(q.cursor, 0);
});

test('Unchanged enforces the pre/post invariant for a real implementation', async () => {
  const p = new InterfacePlayback();
  await p.load([{ call: { fn_name: 'check', obj: { $free: true } },
    before: { args: [{ $new: 'one', $type: 'builtins.dict', keys: ['status'], items: { status: 'same' } }], kwargs: {} },
    after: { args: [{ $unchanged: true }], kwargs: {} }, result: { return: 'ok' } }]);
  const object = { status: 'same' };
  await assert.rejects(p.test(arg => { arg.status = 'different'; return 'ok'; }, Free, 'check', [object]), /Unchanged invariant violated/);
  assert.equal(p.cursor, 0);
  const unchanged = { status: 'same' };
  assert.equal(await p.test(() => 'ok', Free, 'check', [unchanged]), 'ok');
});

test('selective Unchanged only checks selected fields', async () => {
  const p = new InterfacePlayback();
  await p.load([{ call: { fn_name: 'check', obj: { $free: true } },
    before: { args: [{ $new: 'one', $type: 'builtins.dict', keys: ['mode', 'count'], items: { mode: 'same', count: 0 } }], kwargs: {} },
    after: { args: [{ $unchanged: { keys: ['mode'] } }], kwargs: {} }, result: { return: 1 } }]);
  const obj = { mode: 'same', count: 0 };
  assert.equal(await p.test(arg => { arg.count++; return 1; }, Free, 'check', [obj]), 1);
  p.reset();
  const changed = { mode: 'same', count: 0 };
  await assert.rejects(p.test(arg => { arg.mode = 'wrong'; return 1; }, Free, 'check', [changed]), /selected Unchanged invariant violated/);
});

test('duplicate logical introduction across interactions is rejected', async () => {
  const p = new InterfacePlayback();
  const one = { call: { fn_name: 'a', obj: { $free: true } },
    before: { args: [{ $new: 'x', $type: 'builtins.dict', items: {} }], kwargs: {} },
    after: { args: [{ $ref: 'x' }], kwargs: {} }, result: { return: 1 } };
  const two = structuredClone(one);
  two.call.fn_name = 'b';
  await assert.rejects(p.load([one, two]), /duplicate \$new x/);
});

test('unknown and forward references reject before a call executes', async () => {
  const p = new InterfacePlayback();
  const one = { call: { fn_name: 'a', obj: { $free: true } },
    before: { args: [{ $ref: 'later' }], kwargs: {} },
    after: { args: [{ $new: 'later', $type: 'builtins.dict', items: {} }], kwargs: {} },
    result: { return: 1 } };
  await assert.rejects(p.load([one]), /unknown or forward \$ref later/);
});

test('bounded JSONL input replays lazily, resets and saves', async () => {
  const p = new InterfacePlayback();
  for (let i = 0; i < 1100; i++) {
    await p.record(id, n => n + 1, Free, 'increment', [i]);
  }
  const dir = await mkdtemp(join(tmpdir(), 'rwf670-stream-'));
  const file = join(dir, 'source.jsonl');
  const copyFile = join(dir, 'copy.jsonl');
  await p.save(file);
  const q = new InterfacePlayback();
  await q.load(file);
  assert.equal(q.entries.length, 0, 'lazy input does not materialize interaction array');
  assert.equal(q.replay(Free, 'increment', [0]), 1);
  assert.equal(q.replay(Free, 'increment', [1]), 2);
  q.reset();
  assert.equal(q.replay(Free, 'increment', [0]), 1);
  await q.save(copyFile);
  assert.equal(await readFile(copyFile, 'utf8'), await readFile(file, 'utf8'));
  assert.equal(q.cursor, 1, 'independent save does not advance cursor');
});

test('JSONL duplicate identity fails during load scan', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'rwf670-invalid-'));
  const file = join(dir, 'duplicate.jsonl');
  const { writeFile } = await import('node:fs/promises');
  const item = { call: { fn_name: 'x', obj: { $free: true } },
    before: { args: [{ $new: 'a', $type: 'builtins.list', items: [] }], kwargs: {} },
    after: { args: [{ $ref: 'a' }], kwargs: {} }, result: { return: 1 } };
  await writeFile(file, JSON.stringify(item) + '\n' + JSON.stringify(item) + '\n');
  const q = new InterfacePlayback();
  await assert.rejects(q.load(file), /duplicate \$new a/);
});

test('JSONL malformed late entry fails before replay', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'rwf670-late-'));
  const file = join(dir, 'truncated.jsonl');
  const { writeFile } = await import('node:fs/promises');
  const valid = { call: { fn_name: 'ok', obj: { $free: true } },
    before: { args: [], kwargs: {} }, after: { args: [], kwargs: {} },
    result: { return: 1 } };
  await writeFile(file, JSON.stringify(valid) + '\n{"call":');
  const q = new InterfacePlayback();
  await assert.rejects(q.load(file), /malformed\/truncated JSONL/);
});

test('streamed wrong call does not consume next entry', async () => {
  const p = new InterfacePlayback();
  await p.record(id, () => 12, Free, 'correct');
  const dir = await mkdtemp(join(tmpdir(), 'rwf670-wrong-'));
  const file = join(dir, 'x.jsonl');
  await p.save(file);
  const q = new InterfacePlayback();
  await q.load(file);
  assert.throws(() => q.replay(Free, 'incorrect'), /expected correct/);
  assert.equal(q.cursor, 0);
  assert.equal(q.replay(Free, 'correct'), 12);
});

test('distinct equal objects do not alias in streamed replay', async () => {
  const p = new InterfacePlayback();
  await p.record(id, () => true, Free, 'distinct', [{ v: 1 }, { v: 1 }]);
  const dir = await mkdtemp(join(tmpdir(), 'rwf670-distinct-'));
  const file = join(dir, 'x.jsonl');
  await p.save(file);
  const q = new InterfacePlayback();
  await q.load(file);
  const obj = { v: 1 };
  assert.throws(() => q.replay(Free, 'distinct', [obj, obj]), /identity mismatch|duplicate \$new|distinct logical identities/);
  assert.equal(q.cursor, 0);
  assert.equal(q.replay(Free, 'distinct', [{ v: 1 }, { v: 1 }]), true);
});

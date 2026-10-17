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
  assert.equal(check.entries.length, 0, 'JSONL is not materialized in memory');
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

test('rejects missing introduction type and conflicting result variants', async () => {
  const q = new InterfacePlayback();
  const fixture = { call: { fn_name: 'bad', obj: { $free: true } },
    before: { args: [{ $new: 'u', items: [] }], kwargs: {} },
    after: { args: [{ $ref: 'u' }], kwargs: {} },
    result: { return: 1 } };
  await assert.rejects(q.load([fixture]), /\$new requires stable \$type/);
  fixture.before.args[0].$type = 'builtins.list';
  fixture.result.raise = { $type: 'TypeError', args: ['oops'] };
  await assert.rejects(q.load([fixture]), /exactly one return or raise/);
});

test('unknown raised exception type fails explicitly instead of coercion', async () => {
  const p = new InterfacePlayback();
  await p.load([{ call: { fn_name: 'fail', obj: { $free: true } },
    before: { args: [], kwargs: {} }, after: { args: [], kwargs: {} },
    result: { raise: { $type: 'ArbitraryCustomFailure', args: ['bad'] } } }]);
  assert.throws(() => p.replay(Free, 'fail'), /unresolved exception type/);
});

test('recording-wide identities survive sequential calls through streaming', async () => {
  const p = new InterfacePlayback();
  const state = { n: 0 };
  await p.record(id, () => ++state.n, state, 'next');
  await p.record(id, () => ++state.n, state, 'next');
  const dir = await mkdtemp(join(tmpdir(), 'rwf670-repeat-'));
  const file = join(dir, 'seq.jsonl');
  await p.save(file);
  const q = new InterfacePlayback();
  await q.load(file);
  const replica = { n: 0 };
  assert.equal(q.replay(replica, 'next'), 1);
  assert.equal(q.replay(replica, 'next'), 2);
  assert.equal(replica.n, 2);
  assert.throws(() => q.replay(replica, 'next'), /exhausted/);
});

test('real isolated host-call boundary supports capture and replay', async () => {
  const host = { calls: 0, last: null };
  const p = new InterfacePlayback();
  const request = { operation: 'synthetic', count: 2 };
  const send = body => {
    host.calls++;
    host.last = body.operation;
    body.count++;
    return { ok: true, count: body.count };
  };
  const actual = await p.record(id, send, Free, 'host.send', [request]);
  assert.deepEqual(actual, { ok: true, count: 3 });
  assert.equal(host.calls, 1);
  const dir = await mkdtemp(join(tmpdir(), 'rwf670-host-'));
  const file = join(dir, 'host.jsonl');
  await p.save(file);
  const q = new InterfacePlayback();
  await q.load(file);
  const replica = { operation: 'synthetic', count: 2 };
  assert.deepEqual(q.replay(Free, 'host.send', [replica]), { ok: true, count: 3 });
  assert.equal(replica.count, 3);
  assert.equal(host.calls, 1, 'replay never invokes the real host');
});

test('returned reference applies consequential state and preserves alias', async () => {
  const p = new InterfacePlayback();
  await p.load([{ call: { fn_name: 'update', obj: { $free: true } },
    before: { args: [{ $new: 'x', $type: 'builtins.dict', keys: ['v'], items: { v: 1 } }], kwargs: {} },
    after: { args: [{ $ref: 'x', items: {} }], kwargs: {} },
    result: { return: { $ref: 'x', items: { v: 4 } } } }]);
  const arg = { v: 1 };
  assert.equal(p.replay(Free, 'update', [arg]), arg);
  assert.equal(arg.v, 4);
});

test('member mutation can reassign property to existing different reference', async () => {
  const p = new InterfacePlayback();
  await p.load([{ call: { fn_name: 'rebind', obj: { $free: true } },
    before: { args: [
      { $new: 'outer', $type: 'builtins.dict', keys: ['child'], items: {
        child: { $new: 'first', $type: 'builtins.dict', keys: ['id'], items: { id: 1 } } } },
      { $new: 'second', $type: 'builtins.dict', keys: ['id'], items: { id: 2 } }
    ], kwargs: {} }, after: { args: [
      { $ref: 'outer', items: { child: { $ref: 'second' } } },
      { $ref: 'second', items: { id: 2 } }
    ], kwargs: {} }, result: { return: true } }]);
  const first = { id: 1 }, second = { id: 2 }, outer = { child: first };
  assert.equal(p.replay(Free, 'rebind', [outer, second]), true);
  assert.equal(outer.child, second);
  assert.notEqual(outer.child, first);
});

test('unresolvable recorded exception leaves cursor and arguments unchanged', async () => {
  const p = new InterfacePlayback();
  await p.load([{ call: { fn_name: 'fail', obj: { $free: true } },
    before: { args: [{ $new: 'x', $type: 'builtins.dict', keys: ['v'], items: { v: 1 } }], kwargs: {} },
    after: { args: [{ $ref: 'x', items: { v: 2 } }], kwargs: {} },
    result: { raise: { $type: 'NoResolver', args: ['cannot instantiate'] } } }]);
  const value = { v: 1 };
  assert.throws(() => p.replay(Free, 'fail', [value]), /unresolved exception type/);
  assert.equal(p.cursor, 0);
  assert.equal(value.v, 1);
});

test('unsupported intrinsic and sparse arrays fail without recording', async () => {
  const values = [new RegExp('x'), new Error('no'), new Map(), new Set(),
    new Date(), new Uint8Array([1]), new Array(2)];
  for (const value of values) {
    const p = new InterfacePlayback();
    await assert.rejects(p.record(id, () => value, Free, 'unsupported'), /unsupported|sparse/);
    assert.equal(p.entries.length, 0);
  }
});

test('unknown custom result type requires explicit trusted resolver', async () => {
  const record = { call: { fn_name: 'object', obj: { $free: true } },
    before: { args: [], kwargs: {} }, after: { args: [], kwargs: {} },
    result: { return: { $new: 'c', $type: 'CustomThing', value: 2 } } };
  const p = new InterfacePlayback();
  await p.load([record]);
  assert.throws(() => p.replay(Free, 'object'), /unresolved custom type/);
  assert.equal(p.cursor, 0);
  class CustomThing {}
  const q = new InterfacePlayback({ types: { CustomThing } });
  await q.load([record]);
  const value = q.replay(Free, 'object');
  assert.equal(value instanceof CustomThing, true);
  assert.equal(value.value, 2);
});

test('saving directly over current lazy input fails without truncation', async () => {
  const p = new InterfacePlayback();
  await p.record(id, () => 1, Free, 'one');
  const dir = await mkdtemp(join(tmpdir(), 'rwf670-samefile-'));
  const file = join(dir, 'one.jsonl');
  await p.save(file);
  const before = await readFile(file, 'utf8');
  const q = new InterfacePlayback();
  await q.load(file);
  await assert.rejects(q.save(file), /cannot replace an active streaming input/);
  assert.equal(await readFile(file, 'utf8'), before);
});

test('UTF-8 scalar crossing the 16 KiB read boundary survives lazy playback', async () => {
  const p = new InterfacePlayback();
  const value = 'a'.repeat(16379) + '🙂' + 'é';
  await p.record(id, () => value, Free, 'unicode');
  const dir = await mkdtemp(join(tmpdir(), 'rwf670-unicode-'));
  const file = join(dir, 'unicode.jsonl');
  await p.save(file);
  const q = new InterfacePlayback();
  await q.load(file);
  assert.equal(q.replay(Free, 'unicode'), value);
});

test('oversized JSONL interaction is rejected by bounded reader', async () => {
  const { writeFile } = await import('node:fs/promises');
  const dir = await mkdtemp(join(tmpdir(), 'rwf670-cap-'));
  const file = join(dir, 'oversized.jsonl');
  await writeFile(file, JSON.stringify({ call: { fn_name: 'large', obj: { $free: true } },
    before: { args: [], kwargs: {} }, after: { args: [], kwargs: {} },
    result: { return: 'z'.repeat(1100000) } }) + '\n');
  const q = new InterfacePlayback();
  await assert.rejects(q.load(file), /bounded maximum/);
});

test('custom bounded line limit accepts larger certified interactions', async () => {
  const p = new InterfacePlayback();
  const payload = 'y'.repeat(1200000);
  await p.record(id, () => payload, Free, 'large');
  const dir = await mkdtemp(join(tmpdir(), 'rwf670-config-cap-'));
  const file = join(dir, 'large.jsonl');
  await p.save(file);
  const q = new InterfacePlayback({ maxLineBytes: 1300000 });
  await q.load(file);
  assert.equal(q.replay(Free, 'large'), payload);
});

test('inherited prototype type names are not trusted resolvers', async () => {
  const record = { call: { fn_name: 'x', obj: { $free: true } },
    before: { args: [], kwargs: {} }, after: { args: [], kwargs: {} },
    result: { return: { $new: 'untrusted', $type: 'constructor' } } };
  const p = new InterfacePlayback();
  await p.load([record]);
  assert.throws(() => p.replay(Free, 'x'), /unresolved custom type/);
  assert.equal(p.cursor, 0);
});

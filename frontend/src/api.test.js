import test from 'node:test';
import assert from 'node:assert/strict';
import { createApi } from './api.js';

test('creating and updating send only note input, using the correct method', async () => {
  const calls = [];
  const api = createApi('/api', async (url, options) => {
    calls.push({ url, ...options });
    return new Response(JSON.stringify({ id: 'abc' }), { status: 200 });
  });
  await api.save({ title: 'Title', content: 'Body', environment: 'must-not-leak' });
  await api.save({ id: 'abc', title: 'Edited', content: 'Body' });
  assert.equal(calls[0].url, '/api/notes');
  assert.equal(calls[0].method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].body), { title: 'Title', content: 'Body' });
  assert.equal(calls[1].method, 'PUT');
  assert.equal(calls[1].url, '/api/notes/abc');
});
test('a failed request exposes correlation IDs without echoing server content', async () => {
  const api = createApi('/api', async () => new Response('private database details', {
    status: 500, headers: { 'X-Request-Id': 'request-1', 'X-Trace-Id': 'trace-1' },
  }));
  await assert.rejects(api.list(), (error) => {
    assert.equal(error.message, 'Request failed (500)');
    assert.equal(error.requestId, 'request-1');
    assert.equal(error.traceId, 'trace-1');
    return true;
  });
});
test('delete accepts an empty 204 response', async () => {
  const api = createApi('/api', async () => new Response(null, { status: 204 }));
  assert.equal(await api.remove('abc'), null);
});
test('configuration cannot redirect note data to another origin', () => {
  assert.throws(() => createApi('https://another-origin.example/api'));
});

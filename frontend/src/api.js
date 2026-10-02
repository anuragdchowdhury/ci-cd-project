export function createApi(base = '/api', fetcher = globalThis.fetch) {
  if (base !== '/api') throw new Error('This lab uses a same-origin /api endpoint');
  async function request(path, options = {}) {
    const response = await fetcher(`${base}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    });
    if (!response.ok) {
      const error = new Error(`Request failed (${response.status})`);
      error.requestId = response.headers.get('X-Request-Id');
      error.traceId = response.headers.get('X-Trace-Id');
      throw error;
    }
    return response.status === 204 ? null : response.json();
  }
  return {
    list: (page = 0) => request(`/notes?page=${page}&size=20`),
    save: (note) => request(note.id ? `/notes/${encodeURIComponent(note.id)}` : '/notes', {
      method: note.id ? 'PUT' : 'POST',
      body: JSON.stringify({ title: note.title, content: note.content }),
    }),
    remove: (id) => request(`/notes/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  };
}

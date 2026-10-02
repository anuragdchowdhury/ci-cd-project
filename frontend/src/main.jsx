import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { createApi } from './api.js';
import { initializeTelemetry } from './telemetry.js';
import './styles.css';

const config = window.__APP_CONFIG__ ?? { apiBase: '/api', environment: 'local' };
initializeTelemetry(config);
const api = createApi(config.apiBase);
const blank = () => ({ title: '', content: '' });

function App() {
  const [notes, setNotes] = useState([]);
  const [note, setNote] = useState(blank);
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState('');
  async function load(currentPage = page) {
    const result = await api.list(currentPage);
    setNotes(result.items); setTotal(result.total);
  }
  useEffect(() => {
    let current = true;
    api.list(page).then((result) => { if (current) { setNotes(result.items); setTotal(result.total); } })
      .catch((e) => { if (current) setError(e); });
    return () => { current = false; };
  }, [page]);
  async function save(event) {
    event.preventDefault(); setBusy(true); setError(null); setStatus('');
    try { const saved = await api.save(note); setNote(saved); await load(); setStatus('Note saved.'); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function remove() {
    if (!note.id || !window.confirm('Delete this note?')) return;
    setBusy(true); setError(null); setStatus('');
    try { await api.remove(note.id); setNote(blank()); await load(); setStatus('Note deleted.'); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  function select(next) {
    setNote(next);
    setStatus('');
    setError(null);
    if (!next.id) {
      setTimeout(() => document.getElementById('title')?.focus(), 0);
    }
  }
  return <main className="shell">
    <header className="topbar"><a className="brand" href="/">N<span>NoteKeeper</span></a>
      <span className="environment">{config.environment}</span></header>
    <section className="intro"><p className="eyebrow">YOUR IDEAS, IN ONE PLACE</p>
      <h1>A little space to think.</h1><p>Create a note. Make a change. Watch the journey through Azure.</p></section>
    <div className="workspace">
      <aside className="notes-panel"><div className="panel-heading"><h2>Your notes <span>{total}</span></h2>
        <button disabled={busy} onClick={() => select(blank())} className="small">+ New</button></div>
        {notes.length === 0 ? <p className="empty">Your notebook starts here.<br/>Create your first note on the right.</p> :
          <ul className="note-list">{notes.map((item) => <li key={item.id}>
            <button disabled={busy} className={note.id === item.id ? 'note-card selected' : 'note-card'} onClick={() => select(item)}>
              <strong>{item.title}</strong><p>{item.content || 'No content yet'}</p>
              <time>{new Date(item.updatedAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</time>
            </button></li>)}</ul>}
        <div className="pagination"><button disabled={page === 0 || busy} onClick={() => setPage(page - 1)}>Previous</button>
          <span>{page + 1}</span><button disabled={(page + 1) * 20 >= total || busy} onClick={() => setPage(page + 1)}>Next</button></div>
      </aside>
      <section className="editor-panel"><div className="editor-top"><span>{note.id ? 'EDIT NOTE' : 'NEW NOTE'}</span><span>✎</span></div>
        <form onSubmit={save}><label htmlFor="title">Title</label>
          <input id="title" required maxLength={160} value={note.title} disabled={busy} placeholder="Give your idea a title…"
            onChange={(e) => setNote({ ...note, title: e.target.value })}/>
          <label htmlFor="content">Note</label><textarea id="content" maxLength={10000} value={note.content} disabled={busy}
            placeholder="What’s on your mind?" onChange={(e) => setNote({ ...note, content: e.target.value })}/>
          <div className="editor-footer"><span>{note.content.length.toLocaleString()} / 10,000 characters</span>
            <div>{note.id && <button type="button" className="delete" disabled={busy} onClick={remove}>Delete</button>}
              <button type="submit" className="primary" disabled={busy || !note.title.trim()}>{busy ? 'Working…' : 'Save note'}</button></div></div>
        </form>
        {status && <p className="success" role="status">{status}</p>}
        {error && <div className="error" role="alert"><strong>{error.message}</strong>
          {error.requestId && <p>Request: <code>{error.requestId}</code></p>}
          {error.traceId && <p>Trace: <code>{error.traceId}</code></p>}</div>}
      </section>
    </div>
    <footer className="footer">A NOTEKEEPER DEPLOYMENT LAB <span>React · Spring Boot · PostgreSQL</span></footer>
  </main>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App/></React.StrictMode>);

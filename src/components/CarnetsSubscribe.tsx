import React, {useState} from 'react';

type Labels = {
  placeholder: string;
  button: string;
  sending: string;
  done: string;
  error: string;
  privacy: string;
};

const SUBSCRIBE_URL = 'https://n8n.devandre.sbs/webhook/newsletter-subscribe';

// Subscribe box for the Carnets de MiniCloud newsletter.
// POSTs the email to a public n8n webhook (double opt-in: the backend emails a
// confirmation link). URL-encoded body = a CORS "simple" request, so no preflight.
export default function CarnetsSubscribe({labels}: {labels: Labels}): React.ReactElement {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'sending' | 'done' | 'error'>('idle');
  const [msg, setMsg] = useState('');

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus('sending');
    try {
      const res = await fetch(SUBSCRIBE_URL, {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'email=' + encodeURIComponent(email),
      });
      const data = await res.json().catch(() => ({} as {ok?: boolean; message?: string}));
      if (res.ok && data.ok !== false) {
        setStatus('done');
        setMsg(data.message || labels.done);
      } else {
        setStatus('error');
        setMsg(data.message || labels.error);
      }
    } catch {
      setStatus('error');
      setMsg(labels.error);
    }
  }

  if (status === 'done') {
    return (
      <div style={{background: '#ecfdf5', border: '1px solid #a7f3d0', color: '#065f46', borderRadius: 10, padding: '16px 18px', margin: '1.25rem 0', fontSize: 15}}>
        ✓ {msg}
      </div>
    );
  }

  return (
    <div style={{margin: '1.25rem 0'}}>
      <form onSubmit={onSubmit} style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={labels.placeholder}
          aria-label={labels.placeholder}
          style={{flex: '1 1 240px', minWidth: 0, padding: '11px 14px', borderRadius: 8, border: '1px solid #cbd5e1', fontSize: 15}}
        />
        <button
          type="submit"
          disabled={status === 'sending'}
          style={{padding: '11px 24px', borderRadius: 8, border: 'none', background: '#0e7490', color: '#fff', fontWeight: 600, fontSize: 15, cursor: 'pointer', opacity: status === 'sending' ? 0.7 : 1}}>
          {status === 'sending' ? labels.sending : labels.button}
        </button>
      </form>
      {status === 'error' && <div style={{color: '#b91c1c', fontSize: 14, marginTop: 8}}>{msg}</div>}
      <div style={{color: '#64748b', fontSize: 12.5, marginTop: 10, lineHeight: 1.6}}>{labels.privacy}</div>
    </div>
  );
}

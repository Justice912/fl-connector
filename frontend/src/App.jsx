import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  Check,
  Download,
  Gauge,
  Layers3,
  ListMusic,
  Music2,
  Play,
  PlugZap,
  RefreshCw,
  Send,
  SlidersHorizontal,
  Sparkles,
  Square,
  TerminalSquare,
} from 'lucide-react';
import { api } from './api';

const DEFAULT_PROMPT = 'Create an 8-bar deep amapiano song draft in A minor at 113 BPM with FPC drums, soft bass, warm chords, log drum, and a sparse top melody.';

function Stat({ icon: Icon, label, value, tone = 'neutral' }) {
  return (
    <div className={`stat stat-${tone}`}>
      <Icon size={18} aria-hidden="true" />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PianoRollPreview({ payload }) {
  const notes = payload?.notes ?? [];
  const bars = payload?.bars ?? 4;
  const totalBeats = bars * 4;
  const minPitch = notes.length ? Math.min(...notes.map((note) => note.pitch)) - 2 : 45;
  const maxPitch = notes.length ? Math.max(...notes.map((note) => note.pitch)) + 2 : 84;
  const pitchRange = Math.max(1, maxPitch - minPitch);
  const rows = Array.from({ length: Math.min(24, pitchRange + 1) });
  const colorMap = ['#a0aec0', '#ef4444', '#2dd4bf', '#f59e0b', '#8b5cf6', '#38bdf8', '#f472b6', '#84cc16', '#f8fafc'];

  return (
    <section className="panel preview-panel">
      <div className="panel-title">
        <div>
          <p>MIDI preview</p>
          <h2>{payload ? payload.title : 'No draft yet'}</h2>
        </div>
        <ListMusic size={21} aria-hidden="true" />
      </div>
      <div className="roll-shell" aria-label="Generated MIDI note preview">
        <div
          className="roll-grid"
          style={{
            '--beats': totalBeats,
            '--rows': rows.length,
          }}
        >
          {rows.map((_, index) => (
            <span key={index} className="roll-row" />
          ))}
          {Array.from({ length: totalBeats + 1 }).map((_, index) => (
            <span key={index} className="roll-beat" style={{ left: `${(index / totalBeats) * 100}%` }} />
          ))}
          {notes.map((note, index) => {
            const width = Math.max(1.4, (note.durationBeats / totalBeats) * 100);
            const left = (note.startBeats / totalBeats) * 100;
            const bottom = ((note.pitch - minPitch) / pitchRange) * 100;
            return (
              <span
                key={`${note.pitch}-${note.startBeats}-${index}`}
                className="note-block"
                style={{
                  left: `${left}%`,
                  width: `${width}%`,
                  bottom: `${bottom}%`,
                  background: colorMap[note.color] ?? colorMap[0],
                  opacity: 0.62 + note.velocity * 0.32,
                }}
                title={`MIDI ${note.pitch} at beat ${note.startBeats}`}
              />
            );
          })}
        </div>
      </div>
      <div className="preview-meta">
        <span>{notes.length} notes</span>
        <span>{payload?.key ?? 'A'} {payload?.scale ?? 'minor'}</span>
        <span>{payload?.bpm ?? 113} BPM</span>
      </div>
    </section>
  );
}

function EventLog({ events }) {
  return (
    <section className="panel log-panel">
      <div className="panel-title compact">
        <div>
          <p>Event log</p>
          <h2>Connector trace</h2>
        </div>
        <TerminalSquare size={20} aria-hidden="true" />
      </div>
      <div className="events">
        {(events ?? []).length === 0 ? (
          <p className="empty">No events yet.</p>
        ) : (
          events.map((event, index) => (
            <div className="event-row" key={`${event.kind}-${index}`}>
              <span>{event.kind}</span>
              <p>{event.message}</p>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

function BridgePanel({ bridge, setupPlan, busy, onRefresh, onRefreshSetup, onInstallScripts, onTransportAction }) {
  const status = bridge?.status ?? 'disconnected';
  const connected = status === 'connected';
  const errored = status === 'error';
  const tone = connected ? 'good' : errored ? 'bad' : 'warn';
  const transport = bridge?.transport;
  const setupStatus = setupPlan?.status ?? 'needs_action';
  const setupReady = setupStatus === 'ready';

  return (
    <section className="panel bridge-panel" id="bridge">
      <div className="panel-title compact">
        <div>
          <p>Live FL bridge</p>
          <h2>{connected ? 'Read-only snapshot online' : 'Waiting for Flapi'}</h2>
        </div>
        <PlugZap size={20} aria-hidden="true" />
      </div>

      <div className="bridge-head">
        <span className={`bridge-badge ${tone}`}>{status}</span>
        <div className="bridge-actions">
          <button className="secondary-button compact-button" disabled={busy} onClick={onRefreshSetup}>
            <RefreshCw size={18} />
            Refresh Setup
          </button>
          <button className="secondary-button compact-button" disabled={busy} onClick={onRefresh}>
            <RefreshCw size={18} />
            Refresh Bridge
          </button>
        </div>
      </div>

      <p className="bridge-message">
        {bridge?.message ?? 'Bridge status has not been checked yet.'}
      </p>

      <div className="transport-actions" aria-label="Live FL transport controls">
        <span>Transport control</span>
        <button
          className="secondary-button compact-button"
          disabled={busy || !connected}
          onClick={() => onTransportAction('play')}
        >
          <Play size={17} />
          Play
        </button>
        <button
          className="secondary-button compact-button"
          disabled={busy || !connected}
          onClick={() => onTransportAction('stop')}
        >
          <Square size={17} />
          Stop
        </button>
      </div>

      {connected ? (
        <>
          <div className="bridge-summary">
            <div>
              <span>Project</span>
              <strong>{bridge.projectTitle ?? 'Untitled'}</strong>
            </div>
            <div>
              <span>FL version</span>
              <strong>{bridge.flVersion ?? 'Unknown'}</strong>
            </div>
            <div>
              <span>Tracks</span>
              <strong>{bridge.trackCount ?? 0}</strong>
            </div>
            <div>
              <span>Selected</span>
              <strong>{bridge.selectedTrack ?? 'None'}</strong>
            </div>
            <div>
              <span>Transport</span>
              <strong>{transport?.playing ? 'Playing' : 'Stopped'}</strong>
            </div>
            <div>
              <span>Tempo</span>
              <strong>{transport?.tempo ? `${transport.tempo} BPM` : 'Unknown'}</strong>
            </div>
          </div>
          <div className="bridge-tracks">
            {(bridge.tracks ?? []).map((track) => (
              <div className={`bridge-track ${track.selected ? 'selected' : ''}`} key={track.index}>
                <span>{track.index}</span>
                <div>
                  <strong>{track.name || `Track ${track.index}`}</strong>
                  <small>
                    Vol {track.volume ?? 'n/a'} · Pan {track.pan ?? 'n/a'}
                  </small>
                  {track.slots.length > 0 && <em>{track.slots.join(', ')}</em>}
                </div>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="bridge-setup">
          {(bridge?.setup ?? []).map((step, index) => (
            <div className="setup-step" key={step}>
              <span>{index + 1}</span>
              <p>{step}</p>
            </div>
          ))}
        </div>
      )}

      {(bridge?.errors ?? []).length > 0 && (
        <div className="bridge-errors">
          {bridge.errors.map((error) => <span key={error}>{error}</span>)}
        </div>
      )}

      <div className="bridge-setup-panel">
        <div className="bridge-setup-title">
          <div>
            <p>Bridge setup</p>
            <h3>{setupReady ? 'Ready for live probe' : 'Setup checklist'}</h3>
          </div>
          <span className={`bridge-badge ${setupReady ? 'good' : 'warn'}`}>{setupStatus.replace('_', ' ')}</span>
        </div>
        <p className="bridge-message">
          {setupPlan?.message ?? 'Setup has not been checked yet.'}
        </p>
        <div className="setup-checks">
          {(setupPlan?.checks ?? []).map((check) => (
            <div className={`setup-check ${check.status}`} key={check.key}>
              <span>{check.status}</span>
              <div>
                <strong>{check.label}</strong>
                <p>{check.detail}</p>
                {check.action && <small>{check.action}</small>}
              </div>
            </div>
          ))}
        </div>
        <div className="setup-actions">
          <button
            className="primary-button"
            disabled={busy || !setupPlan?.canInstallScripts}
            onClick={onInstallScripts}
          >
            <Download size={18} />
            Install Flapi Scripts
          </button>
        </div>
        <div className="manual-steps">
          {(setupPlan?.manualSteps ?? []).map((step, index) => (
            <span key={step}>{index + 1}. {step}</span>
          ))}
        </div>
      </div>
    </section>
  );
}

function SongDraftPanel({ song, selectedPartId, onSelectPart }) {
  if (!song) {
    return (
      <section className="panel song-panel">
        <div className="panel-title compact">
          <div>
            <p>Song draft</p>
            <h2>No grouped draft yet</h2>
          </div>
          <Layers3 size={20} aria-hidden="true" />
        </div>
        <p className="empty">Generate a song draft to get separate FL-ready parts and an arrangement guide.</p>
      </section>
    );
  }

  return (
    <section className="panel song-panel">
      <div className="panel-title compact">
        <div>
          <p>Song draft</p>
          <h2>{song.title}</h2>
        </div>
        <Layers3 size={20} aria-hidden="true" />
      </div>
      <div className="part-list">
        {song.parts.map((part) => (
          <button
            type="button"
            className={`part-row ${part.id === selectedPartId ? 'active' : ''}`}
            key={part.id}
            onClick={() => onSelectPart(part)}
          >
            <span>{part.applyOrder}</span>
            <strong>{part.patternName}</strong>
            <em>{part.pluginHint}</em>
            <small>{part.payload.notes.length} notes</small>
          </button>
        ))}
      </div>
      <div className="arrangement-strip" aria-label="Arrangement guide">
        {song.arrangement.map((section) => (
          <div className="arrangement-section" key={`${section.name}-${section.startBar}`}>
            <strong>{section.name}</strong>
            <span>Bar {section.startBar} - {section.startBar + section.bars - 1}</span>
            <small>{section.activeParts.join(', ')}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function MasteringPanel({ plan, busy, onGenerate, onApprove }) {
  const grouped = (plan?.steps ?? []).reduce((acc, step) => {
    if (!acc[step.target]) acc[step.target] = [];
    acc[step.target].push(step);
    return acc;
  }, {});
  const targets = ['drums', 'bass', 'chords', 'log_drum', 'melody', 'master'].filter((target) => grouped[target]);

  return (
    <section className="panel mastering-panel" id="mastering">
      <div className="panel-title compact">
        <div>
          <p>Mixing and mastering</p>
          <h2>{plan ? plan.title : 'Built-in FL chain'}</h2>
        </div>
        <Sparkles size={20} aria-hidden="true" />
      </div>
      <div className="mastering-actions">
        <button className="secondary-button" disabled={busy} onClick={onGenerate}>
          <Sparkles size={18} />
          Generate Master Chain
        </button>
        <button className="primary-button" disabled={busy || !plan || plan.status !== 'draft'} onClick={onApprove}>
          <Check size={18} />
          Approve Master Chain
        </button>
      </div>
      {plan ? (
        <>
          <div className="mastering-summary">
            <span>Status</span>
            <strong>{plan.status}</strong>
            <span>Target</span>
            <strong>{plan.targetLoudness}</strong>
          </div>
          <div className="mix-targets">
            {targets.map((target) => (
              <div className="mix-target" key={target}>
                <h3>{target.replace('_', ' ')}</h3>
                {grouped[target].map((step) => (
                  <div className="mix-step" key={step.order}>
                    <span>{step.order}</span>
                    <div>
                      <strong>{step.plugin}</strong>
                      <p>{step.action}</p>
                      <small>{step.clickPath}</small>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
          <div className="safety-notes">
            {plan.safetyNotes.map((note) => <span key={note}>{note}</span>)}
          </div>
        </>
      ) : (
        <p className="empty">Generate a chain after your song draft to get Mixer-ready built-in plugin steps.</p>
      )}
    </section>
  );
}

function App() {
  const [health, setHealth] = useState(null);
  const [bridge, setBridge] = useState(null);
  const [bridgeSetup, setBridgeSetup] = useState(null);
  const [events, setEvents] = useState([]);
  const [payload, setPayload] = useState(null);
  const [song, setSong] = useState(null);
  const [masteringPlan, setMasteringPlan] = useState(null);
  const [selectedPartId, setSelectedPartId] = useState('');
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [form, setForm] = useState({ genre: 'Amapiano', bpm: 113, key: 'A', scale: 'minor', bars: 8 });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const paths = health?.paths;
  const exists = paths?.exists ?? {};
  const installed = Boolean(exists.installedScriptPath);
  const scriptReady = installed && Boolean(exists.pianoRollScripts);

  const statusTone = useMemo(() => (scriptReady ? 'good' : 'warn'), [scriptReady]);
  const bridgeConnected = bridge?.status === 'connected';
  const bridgeSetupReady = bridgeSetup?.status === 'ready';
  const selectedPart = useMemo(
    () => song?.parts?.find((part) => part.id === selectedPartId) ?? null,
    [song, selectedPartId],
  );

  async function refresh({ adoptCurrent = true } = {}) {
    const result = await api.health();
    setHealth(result);
    setEvents(result.events ?? []);
    if (adoptCurrent && result.currentSong) {
      setSong(result.currentSong);
      setSelectedPartId((current) => current || result.currentSong.parts?.[0]?.id || '');
    }
    if (adoptCurrent && result.currentMasteringPlan) setMasteringPlan(result.currentMasteringPlan);
    if (adoptCurrent && result.currentPayload) setPayload(result.currentPayload);
  }

  async function refreshBridge() {
    const result = await api.bridgeHealth();
    setBridge(result);
    return result;
  }

  async function refreshBridgeSetup() {
    const result = await api.bridgeSetup();
    setBridgeSetup(result);
    return result;
  }

  useEffect(() => {
    refresh().catch((error) => setMessage(error.message));
    refreshBridgeSetup().catch((error) => {
      setBridgeSetup({
        status: 'error',
        message: error.message,
        canInstallScripts: false,
        checks: [],
        manualSteps: [],
      });
    });
    refreshBridge().catch((error) => {
      setBridge({
        status: 'disconnected',
        message: error.message,
        source: 'frontend',
        tracks: [],
        setup: [],
        errors: [error.message],
      });
    });
  }, []);

  async function runTask(task, options = {}) {
    setBusy(true);
    setMessage('');
    try {
      await task();
      await refresh(options);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  const generated = payload?.status === 'draft';
  const approved = payload?.status === 'approved';

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Music2 size={22} /></div>
          <div>
            <strong>FL Connector</strong>
            <span>2025 local bridge</span>
          </div>
        </div>
        <nav>
          <a className="active" href="#connector"><PlugZap size={18} /> Connector</a>
          <a href="#bridge"><Activity size={18} /> Bridge</a>
          <a href="#prompt"><Send size={18} /> Prompts</a>
          <a href="#payload"><ListMusic size={18} /> Payloads</a>
          <a href="#install"><Download size={18} /> Install</a>
          <a href="#logs"><TerminalSquare size={18} /> Logs</a>
        </nav>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <p>Local FL Studio control surface</p>
            <h1>Song drafting workspace</h1>
          </div>
          <div className="top-actions">
            <button className="icon-button" onClick={() => runTask(refresh)} disabled={busy} aria-label="Refresh health">
              <RefreshCw size={18} />
            </button>
            <span className={`health-pill ${statusTone}`}>
              <Activity size={16} />
              {scriptReady ? 'Script ready' : 'Install needed'}
            </span>
          </div>
        </header>

        <section className="status-grid" id="connector">
          <Stat icon={Gauge} label="FL Studio" value={exists.flStudio2025 ? 'Found' : 'Missing'} tone={exists.flStudio2025 ? 'good' : 'warn'} />
          <Stat icon={ListMusic} label="Piano Roll path" value={exists.pianoRollScripts ? 'Found' : 'Missing'} tone={exists.pianoRollScripts ? 'good' : 'warn'} />
          <Stat icon={Download} label="Writer script" value={installed ? 'Installed' : 'Not installed'} tone={installed ? 'good' : 'warn'} />
          <Stat icon={Layers3} label="Song parts" value={song ? `${song.parts.length} ready` : 'None'} tone={song ? 'good' : 'neutral'} />
          <Stat icon={Sparkles} label="Master chain" value={masteringPlan?.status === 'approved' ? 'Approved' : masteringPlan ? 'Draft' : 'None'} tone={masteringPlan ? 'good' : 'neutral'} />
          <Stat icon={Check} label="Approved payload" value={approved ? 'Ready' : 'None'} tone={approved ? 'good' : 'neutral'} />
          <Stat icon={PlugZap} label="Live bridge" value={bridgeConnected ? 'Connected' : 'Offline'} tone={bridgeConnected ? 'good' : 'warn'} />
          <Stat icon={Activity} label="Bridge setup" value={bridgeSetupReady ? 'Ready' : 'Needs setup'} tone={bridgeSetupReady ? 'good' : 'warn'} />
        </section>

        <BridgePanel
          bridge={bridge}
          setupPlan={bridgeSetup}
          busy={busy}
          onRefresh={() => runTask(refreshBridge, { adoptCurrent: false })}
          onRefreshSetup={() => runTask(refreshBridgeSetup, { adoptCurrent: false })}
          onInstallScripts={() => runTask(async () => {
            await api.installBridgeScripts();
            await refreshBridgeSetup();
            setMessage('Flapi controller scripts installed. Restart FL Studio, then refresh bridge health.');
          }, { adoptCurrent: false })}
          onTransportAction={(action) => runTask(async () => {
            const next = await api.bridgeTransport(action);
            setBridge(next);
            setMessage(`FL transport ${action} command sent.`);
          }, { adoptCurrent: false })}
        />

        <SongDraftPanel
          song={song}
          selectedPartId={selectedPartId}
          onSelectPart={(part) => {
            setSelectedPartId(part.id);
            setPayload(part.payload);
            setMessage(`Selected ${part.patternName}.`);
          }}
        />

        <MasteringPanel
          plan={masteringPlan}
          busy={busy}
          onGenerate={() => runTask(async () => {
            const next = await api.generateMastering({ prompt, genre: form.genre, bpm: form.bpm });
            setMasteringPlan(next);
            setMessage(`Mastering chain generated with ${next.steps.length} steps.`);
          }, { adoptCurrent: false })}
          onApprove={() => runTask(async () => {
            const next = await api.approveMastering(masteringPlan.id);
            setMasteringPlan(next);
            setMessage('Mastering chain approved and written for FL Connector.');
          }, { adoptCurrent: false })}
        />

        <div className="work-grid">
          <section className="panel composer" id="prompt">
            <div className="panel-title">
              <div>
                <p>Prompt composer</p>
                <h2>Generate notes</h2>
              </div>
              <SlidersHorizontal size={21} aria-hidden="true" />
            </div>
            <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} />
            <div className="field-grid">
              <label>
                Genre
                <select value={form.genre} onChange={(event) => setForm({ ...form, genre: event.target.value })}>
                  <option>Amapiano</option>
                  <option>Afrobeats</option>
                  <option>Afrohouse</option>
                  <option>Hip Hop</option>
                </select>
              </label>
              <label>
                BPM
                <input type="number" min="40" max="240" value={form.bpm} onChange={(event) => setForm({ ...form, bpm: Number(event.target.value) })} />
              </label>
              <label>
                Key
                <select value={form.key} onChange={(event) => setForm({ ...form, key: event.target.value })}>
                  {['A', 'C', 'D', 'E', 'F', 'G', 'Bb', 'C#'].map((key) => <option key={key}>{key}</option>)}
                </select>
              </label>
              <label>
                Bars
                <input type="number" min="4" max="32" value={form.bars} onChange={(event) => setForm({ ...form, bars: Number(event.target.value) })} />
              </label>
            </div>
            <div className="composer-actions">
              <button
                className="primary-button"
                disabled={busy || prompt.trim().length < 3}
                onClick={() => runTask(async () => {
                  const next = await api.generateSong({ prompt, ...form, bars: Math.max(4, form.bars) });
                  setSong(next);
                  setSelectedPartId(next.parts[0]?.id ?? '');
                  setPayload(next.parts[0]?.payload ?? null);
                  setMessage(`Song draft generated with ${next.parts.length} parts.`);
                }, { adoptCurrent: false })}
              >
                <Layers3 size={18} />
                Generate Song Draft
              </button>
              <button
                className="secondary-button"
                disabled={busy || prompt.trim().length < 3}
                onClick={() => runTask(async () => {
                  const next = await api.generate({ prompt, ...form });
                  setPayload(next);
                  setMessage('Single part draft generated.');
                }, { adoptCurrent: false })}
              >
                <Send size={18} />
                Generate Single Part
              </button>
            </div>
          </section>

          <PianoRollPreview payload={payload} />

          <section className="panel approval" id="payload">
            <div className="panel-title">
              <div>
                <p>Approval queue</p>
                <h2>{payload ? payload.status : 'Waiting'}</h2>
              </div>
              <Play size={21} aria-hidden="true" />
            </div>
            <div className="payload-summary">
              <span>Target</span>
              <strong>{payload?.target ?? 'current_piano_roll'}</strong>
              <span>Part</span>
              <strong>{selectedPart?.patternName ?? payload?.title ?? 'No part selected'}</strong>
              <span>Clear mode</span>
              <strong>{payload?.clearMode ?? 'none'}</strong>
              <span>Apply path</span>
              <strong>{paths?.payloadPath ?? 'No path loaded'}</strong>
            </div>
            <div className="approval-actions">
              <button
                className="secondary-button"
                disabled={busy}
                onClick={() => runTask(async () => {
                  await api.install();
                  setMessage('Piano Roll script installed.');
                })}
              >
                <Download size={18} />
                Install Script
              </button>
              <button
                className="primary-button"
                disabled={busy || !payload || !generated}
                onClick={() => runTask(async () => {
                  const next = await api.approve(payload.id);
                  setPayload(next);
                  setSong((current) => current
                    ? {
                        ...current,
                        parts: current.parts.map((part) => (
                          part.payload.id === next.id ? { ...part, payload: next } : part
                        )),
                      }
                    : current);
                  setMessage('Selected part approved and written for FL Studio.');
                }, { adoptCurrent: false })}
              >
                <Check size={18} />
                Approve Selected Part
              </button>
            </div>
            <div className="apply-note">
              <strong>FL Studio</strong>
              <span>Open the matching instrument Piano Roll with F7, then run Tools &gt; Scripts &gt; FL Connector Apply Payload.</span>
              {selectedPart && <span>{selectedPart.pluginHint}</span>}
            </div>
          </section>
        </div>

        {message && <div className="toast">{message}</div>}
        <EventLog events={events} />
      </main>
    </div>
  );
}

export default App;

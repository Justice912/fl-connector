import { useEffect, useMemo, useState } from 'react';
import {
  AudioLines,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock,
  Download,
  FileAudio,
  FolderSearch,
  LoaderCircle,
  Music2,
  Play,
  Plus,
  RefreshCw,
  Send,
  SlidersHorizontal,
  Trash2,
  Upload,
  Wrench,
} from 'lucide-react';
import { api } from '../api';

const ACCEPTED_STEMS = '.zip,.wav,.mp3,.flac,.m4a';
const STEM_ROLES = ['drums', 'percussion', 'bass', 'chords', 'log_drum', 'melody', 'vocals', 'guitar', 'fx', 'other'];

function StatusBadge({ status }) {
  const tone = ['review', 'approved', 'complete'].includes(status) ? 'good' : status === 'error' ? 'bad' : 'warn';
  return <span className={`rebuild-badge ${tone}`}>{String(status ?? 'draft').replace('_', ' ')}</span>;
}

function Confidence({ value, requiresReview }) {
  const percent = Math.round((value ?? 0) * 100);
  const tone = percent >= 80 ? 'good' : percent >= 60 ? 'warn' : 'bad';
  return (
    <div className="confidence-line">
      <span className={`confidence-value ${tone}`}>{percent}% confidence</span>
      {requiresReview && <strong>Review required</strong>}
    </div>
  );
}

function acceptanceItems(project) {
  const parts = project.parts ?? [];
  const guideSteps = project.guideSteps ?? [];
  const midiParts = parts.filter((part) => part.outputMode === 'midi');
  const approvedParts = parts.filter((part) => part.approved);
  const missingSoundParts = midiParts.filter((part) => !part.selectedSoundId);
  const completedGuideSteps = guideSteps.filter((step) => step.completed);
  const keyConfidence = project.analysisSummary?.keyConfidence;
  const keyPercent = typeof keyConfidence === 'number' ? Math.round(keyConfidence * 100) : null;
  const keyName = project.analysisSummary ? `${project.analysisSummary.key} ${project.analysisSummary.scale}` : 'not detected';
  return [
    {
      id: 'parts',
      label: 'Parts approved',
      complete: parts.length > 0 && approvedParts.length === parts.length,
      required: true,
      detail: `${approvedParts.length}/${parts.length} parts approved`,
    },
    {
      id: 'sounds',
      label: 'Sound choices',
      complete: missingSoundParts.length === 0,
      required: true,
      detail: missingSoundParts.length
        ? `${missingSoundParts.length} MIDI part${missingSoundParts.length === 1 ? ' needs a sound' : 's need sounds'}`
        : `${midiParts.length}/${midiParts.length} MIDI sounds selected`,
    },
    {
      id: 'guide',
      label: 'FL walkthrough',
      complete: guideSteps.length > 0 && completedGuideSteps.length === guideSteps.length,
      required: true,
      detail: `${completedGuideSteps.length}/${guideSteps.length} guide steps complete`,
    },
    {
      id: 'key',
      label: 'Key check',
      complete: keyPercent === null || keyPercent >= 80,
      required: false,
      detail: keyPercent === null
        ? 'Key confidence not available'
        : `Key confidence ${keyPercent}% for ${keyName}`,
    },
  ];
}

function AcceptanceGate({ project }) {
  if (!project.analysisSummary && project.parts.length === 0 && project.guideSteps.length === 0) return null;
  const items = acceptanceItems(project);
  const openRequired = items.filter((item) => item.required && !item.complete).length;
  return (
    <section className="acceptance-gate">
      <header>
        <div><p>Final handoff</p><h2>Acceptance gate</h2></div>
        <span className={`acceptance-state ${openRequired ? 'open' : 'ready'}`}>{openRequired ? `${openRequired} open` : 'Ready'}</span>
      </header>
      <div className="acceptance-grid">
        {items.map((item) => (
          <article className={item.complete ? 'complete' : item.required ? 'open' : 'review'} key={item.id}>
            <span>{item.complete ? 'Ready' : item.required ? 'Open' : 'Review'}</span>
            <strong>{item.label}</strong>
            <p>{item.detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function MiniPianoRoll({ pattern }) {
  const notes = pattern?.payload?.notes ?? [];
  const totalBeats = Math.max(4, (pattern?.bars ?? 1) * 4);
  const pitches = notes.map((note) => note.pitch);
  const low = pitches.length ? Math.min(...pitches) - 1 : 36;
  const high = pitches.length ? Math.max(...pitches) + 1 : 72;
  const range = Math.max(1, high - low);
  return (
    <div className="mini-roll" aria-label={`${pattern?.name ?? 'Pattern'} Piano Roll preview`}>
      {notes.map((note, index) => (
        <span
          key={`${note.pitch}-${note.startBeats}-${index}`}
          style={{
            left: `${(note.startBeats / totalBeats) * 100}%`,
            width: `${Math.max(1.5, (note.durationBeats / totalBeats) * 100)}%`,
            bottom: `${((note.pitch - low) / range) * 84 + 8}%`,
            opacity: 0.55 + (note.velocity ?? 0.8) * 0.4,
          }}
        />
      ))}
    </div>
  );
}

function ProjectCreator({ busy, onCreate }) {
  const [title, setTitle] = useState('');
  const [rightsAccepted, setRightsAccepted] = useState(false);
  return (
    <section className="rebuild-empty">
      <FileAudio size={28} aria-hidden="true" />
      <div>
        <p>Local audio reconstruction</p>
        <h2>Start a reconstruction</h2>
        <span>Create an editable FL Studio blueprint from stems you own or have permission to use.</span>
      </div>
      <form onSubmit={(event) => { event.preventDefault(); onCreate({ title, rightsAccepted, genreProfile: 'south_african_dance' }); }}>
        <label>
          Project title
          <input value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={160} />
        </label>
        <label className="rights-check">
          <input type="checkbox" checked={rightsAccepted} onChange={(event) => setRightsAccepted(event.target.checked)} />
          <span>I own these stems or have permission to reconstruct them.</span>
        </label>
        <button className="primary-button" type="submit" disabled={busy || !rightsAccepted || !title.trim()}>
          <Plus size={17} /> Create project
        </button>
      </form>
    </section>
  );
}

function SetupBar({ setup, busy, onInstall }) {
  const [approved, setApproved] = useState(false);
  if (setup?.ready) return <div className="setup-strip ready"><Check size={18} /> Local analysis worker ready</div>;
  const missing = setup?.checks?.filter((check) => check.status !== 'ready') ?? [];
  const message = setup
    ? `Setup needed: ${missing.map((check) => check.label).join(', ') || 'review the local prerequisites'}.`
    : 'Checking the local analysis worker.';
  return (
    <div className="setup-strip">
      <Wrench size={18} aria-hidden="true" />
      <span>{message}</span>
      <label className="inline-consent">
        <input type="checkbox" checked={approved} onChange={(event) => setApproved(event.target.checked)} />
        Approve winget and local worker installation
      </label>
      <button className="secondary-button rebuild-inline" disabled={busy || !approved || !setup?.canInstall} onClick={() => onInstall(approved)}>
        Install prerequisites and worker
      </button>
      {(setup?.installPlan ?? []).length > 0 && (
        <div className="setup-install-plan" aria-label="Verified installation plan">
          {setup.installPlan.map((item) => (
            <span key={item.id}>
              <strong>{item.name}</strong>
              <small>{item.publisher} &middot; {item.source}</small>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function UploadBand({ project, busy, selectedFiles, onFiles, onUpload, onAnalyze }) {
  return (
    <section className="upload-band">
      <div className="upload-copy">
        <p>Source stems</p>
        <h2>{project.stems.length ? `${project.stems.length} files ready` : 'Add your exported stems'}</h2>
        <span>ZIP, WAV, MP3, FLAC, or M4A. Up to 20 files, 1 GB total, and 15 minutes per file.</span>
      </div>
      <label className="file-picker">
        <Upload size={18} />
        <span>{selectedFiles.length ? `${selectedFiles.length} selected` : 'Choose files'}</span>
        <input type="file" aria-label="Stem files" accept={ACCEPTED_STEMS} multiple onChange={(event) => onFiles(Array.from(event.target.files ?? []))} />
      </label>
      <button className="secondary-button rebuild-inline" disabled={busy || !selectedFiles.length} onClick={onUpload}>
        <Upload size={17} /> Upload {selectedFiles.length || ''} stem{selectedFiles.length === 1 ? '' : 's'}
      </button>
      <button className="primary-button rebuild-inline" disabled={busy || !project.stems.length} onClick={onAnalyze}>
        <Play size={17} /> Analyze locally
      </button>
    </section>
  );
}

function AnalysisHeader({ project, busy, onCorrect }) {
  const job = project.analysisJob;
  const summary = project.analysisSummary;
  const [correction, setCorrection] = useState({
    bpm: summary?.bpm ?? project.analysisOverrides?.bpm ?? 114,
    key: summary?.key ?? project.analysisOverrides?.key ?? 'G',
    scale: summary?.scale ?? project.analysisOverrides?.scale ?? 'minor',
  });
  useEffect(() => {
    setCorrection({
      bpm: summary?.bpm ?? project.analysisOverrides?.bpm ?? 114,
      key: summary?.key ?? project.analysisOverrides?.key ?? 'G',
      scale: summary?.scale ?? project.analysisOverrides?.scale ?? 'minor',
    });
  }, [project.id, project.updatedAt, summary?.bpm, summary?.key, summary?.scale]);
  return (
    <section className="analysis-band">
      <div className="analysis-progress">
        <div>
          <p>{job?.stage ?? 'Analysis evidence'}</p>
          <h2>{job?.message ?? (summary ? 'Reconstruction ready for review' : 'Waiting for local analysis')}</h2>
        </div>
        {job && <strong>{job.progress}%</strong>}
      </div>
      {job && <progress max="100" value={job.progress}>{job.progress}%</progress>}
      {summary && (
        <div className="analysis-facts">
          <span><small>Tempo</small><strong>{summary.bpm} BPM</strong></span>
          <span><small>Key</small><strong>{summary.key} {summary.scale}</strong></span>
          <span><small>Duration</small><strong>{Math.round(summary.durationSeconds)} sec</strong></span>
          <span><small>Tempo certainty</small><strong>{Math.round(summary.bpmConfidence * 100)}%</strong></span>
          <span><small>Key certainty</small><strong>{Math.round(summary.keyConfidence * 100)}%</strong></span>
        </div>
      )}
      <form className="analysis-correction" onSubmit={(event) => { event.preventDefault(); onCorrect({ ...correction, bpm: Number(correction.bpm) }); }}>
        <label>Correct BPM<input type="number" min="40" max="240" step="0.01" value={correction.bpm} onChange={(event) => setCorrection((value) => ({ ...value, bpm: event.target.value }))} /></label>
        <label>Correct key<input value={correction.key} maxLength={3} onChange={(event) => setCorrection((value) => ({ ...value, key: event.target.value }))} /></label>
        <label>Scale<select value={correction.scale} onChange={(event) => setCorrection((value) => ({ ...value, scale: event.target.value }))}><option value="minor">Minor</option><option value="major">Major</option></select></label>
        <div><small>Corrections clear dependent patterns and require analysis again.</small><button className="secondary-button rebuild-inline" type="submit" disabled={busy}>Save corrections</button></div>
      </form>
    </section>
  );
}

function EvidencePane({ project, client, busy, onPatchPart }) {
  const stemById = useMemo(() => Object.fromEntries(project.stems.map((stem) => [stem.id, stem])), [project.stems]);
  return (
    <section className="evidence-pane">
      <header><div><p>Audio evidence</p><h2>Stems and confidence</h2></div><AudioLines size={20} /></header>
      <div className="stem-evidence-list">
        {project.parts.length === 0 && project.stems.map((stem) => (
          <article className="stem-evidence" key={stem.id}>
            <div><strong>{stem.fileName}</strong><span>{stem.role} · {(stem.sizeBytes / 1024).toFixed(1)} KB</span></div>
            {client.stemContentUrl && <audio controls preload="metadata" src={client.stemContentUrl(project.id, stem.id)} />}
          </article>
        ))}
        {project.parts.map((part) => {
          const stem = stemById[part.sourceStemId];
          return (
            <article className={`stem-evidence ${part.requiresReview ? 'needs-review' : ''}`} key={part.id}>
              <div className="stem-heading">
                <div><strong>{part.name}</strong><span>{part.role.replace('_', ' ')}</span></div>
                <Confidence value={part.confidence} requiresReview={part.requiresReview} />
              </div>
              {stem && client.stemContentUrl && <audio controls preload="metadata" src={client.stemContentUrl(project.id, stem.id)} />}
              <label>
                Role for {part.name}
                <select value={part.role} disabled={busy} onChange={(event) => onPatchPart(part.id, { role: event.target.value })}>
                  {STEM_ROLES.map((role) => <option value={role} key={role}>{role.replace('_', ' ')}</option>)}
                </select>
              </label>
              <label>
                Output mode for {part.name}
                <select
                  value={part.outputMode}
                  disabled={busy}
                  onChange={(event) => onPatchPart(part.id, { outputMode: event.target.value })}
                >
                  <option value="midi">Editable MIDI</option>
                  <option value="audio">Aligned audio</option>
                </select>
              </label>
              {project.soundMatches.length > 0 && <label>
                Sound for {part.name}
                <select value={part.selectedSoundId ?? ''} disabled={busy} onChange={(event) => onPatchPart(part.id, { selectedSoundId: event.target.value })}>
                  <option value="">Choose a recommendation</option>
                  {project.soundMatches.map((match) => <option value={match.id} key={match.id}>{match.name}{match.installed ? ' (installed)' : ''}</option>)}
                </select>
              </label>}
              <small>{part.instrumentHint}</small>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function BlueprintPane({ project, client, busy, onProjectChange }) {
  return (
    <section className="blueprint-pane">
      <header><div><p>FL blueprint</p><h2>Channel Rack and Piano Roll</h2></div><SlidersHorizontal size={20} /></header>
      <div className="channel-blueprint">
        {project.parts.length === 0 && <p className="rebuild-muted">Analyze the uploaded stems to compile the editable channel plan.</p>}
        {project.parts.map((part, index) => (
          <article className="blueprint-channel" key={part.id}>
            <div className="channel-order">{index + 1}</div>
            <div className="channel-details">
              <div className="channel-title"><strong>{part.name}</strong><span>{part.outputMode}</span></div>
              <p>{part.instrumentHint}</p>
              {part.patterns.map((pattern) => (
                <div className="pattern-row" key={pattern.id}>
                  <div><strong>{pattern.name}</strong><span>Bar {pattern.startBar} · {pattern.bars} bars</span></div>
                  <MiniPianoRoll pattern={pattern} />
                  <button
                    className="secondary-button rebuild-inline"
                    disabled={busy || pattern.payload.status === 'approved'}
                    aria-label={`Approve ${pattern.name}`}
                    onClick={async () => {
                      const result = await client.approveReconstructionPattern(project.id, part.id, pattern.id);
                      onProjectChange(result.project ?? result);
                    }}
                  >
                    <Check size={16} /> {pattern.payload.status === 'approved' ? 'Approved' : 'Approve MIDI'}
                  </button>
                </div>
              ))}
              {part.outputMode === 'audio' && (
                <button
                  className="secondary-button rebuild-inline"
                  disabled={busy || part.approved}
                  onClick={async () => onProjectChange(await client.approveReconstructionAudio(project.id, part.id))}
                >
                  <Check size={16} /> {part.approved ? 'Audio approved' : 'Approve aligned audio'}
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function Arrangement({ project }) {
  if (!project.timeline.length) return null;
  return (
    <section className="rebuild-section">
      <header><div><p>Playlist map</p><h2>Arrangement sections</h2></div><Music2 size={20} /></header>
      <div className="timeline-map">
        {project.timeline.map((section) => (
          <div key={section.id} style={{ flexGrow: Math.max(1, section.bars) }}>
            <strong>{section.name}</strong><span>Bar {section.startBar}</span><small>{section.bars} bars</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function Recommendations({ matches, onRefresh, busy }) {
  return (
    <section className="rebuild-section">
      <header>
        <div><p>Sound matching</p><h2>Installed first</h2></div>
        <button className="icon-button" aria-label="Refresh instrument inventory" disabled={busy} onClick={onRefresh}><FolderSearch size={18} /></button>
      </header>
      <div className="recommendation-list">
        {matches.length === 0 && <p className="rebuild-muted">Refresh inventory after analysis to match installed plugins and samples.</p>}
        {matches.map((match) => (
          <article key={match.id}>
            <span className={`match-state ${match.installed ? 'installed' : 'catalog'}`}>{match.installed ? 'Installed' : match.priceClass}</span>
            <div><strong>{match.name}</strong><p>{match.reason}</p></div>
            {match.url && <a href={match.url} target="_blank" rel="noreferrer">Official source</a>}
          </article>
        ))}
      </div>
    </section>
  );
}

function MixPlan({ plan }) {
  if (!plan?.steps?.length) return null;
  return (
    <section className="rebuild-section">
      <header><div><p>Mixer</p><h2>Built-in FL mix plan</h2></div><SlidersHorizontal size={20} /></header>
      <div className="rebuild-mix-list">
        {plan.steps.map((step) => (
          <article key={`${step.order}-${step.plugin}`}>
            <span>{step.order}</span><div><strong>{step.targetLabel}: {step.plugin}</strong><p>{step.action}</p></div>
          </article>
        ))}
      </div>
    </section>
  );
}

function SyncReportView({ report }) {
  if (!report.connected) {
    return <div className="sync-report disconnected">FL not connected: {report.message}</div>;
  }
  return (
    <div className="sync-report">
      {report.tempo && <p>Tempo set to {report.tempo.value} BPM ({report.tempo.status}).</p>}
      <p>
        {report.channels.length} channel{report.channels.length === 1 ? '' : 's'} named,{' '}
        {report.mixer.length} mixer track{report.mixer.length === 1 ? '' : 's'} named.
      </p>
      {report.skipped.length > 0 && (
        <ul className="sync-skipped">
          {report.skipped.map((skip, index) => (
            <li key={`${skip.kind}-${index}`}>{skip.message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SendToFl({ project, client, busy, onError }) {
  const [report, setReport] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const hasMidi = project.parts.some((part) => part.outputMode === 'midi');

  async function sync() {
    setSyncing(true);
    onError('');
    try {
      setReport(await client.syncReconstructionToFl(project.id));
    } catch (reason) {
      onError(reason.message);
    } finally {
      setSyncing(false);
    }
  }

  return (
    <section className="rebuild-section send-to-fl">
      <header><div><p>Send to FL</p><h2>One-drag handoff</h2></div><Send size={20} /></header>
      <div className="send-to-fl-actions">
        <button
          className="primary-button rebuild-inline"
          disabled={busy || !hasMidi}
          onClick={() => client.exportReconstructionMidi(project.id)}
        >
          <Download size={17} /> Download arrangement MIDI
        </button>
        <button
          className="secondary-button rebuild-inline"
          disabled={busy || syncing}
          onClick={sync}
        >
          <RefreshCw size={17} /> Sync FL to this rebuild
        </button>
      </div>
      <p className="rebuild-muted">
        Drag the MIDI onto the FL Playlist, then click Sync to set tempo and name the channels.
      </p>
      {report && <SyncReportView report={report} />}
    </section>
  );
}

function ExtendSong({ project, client, busy, onError, onProjectChange }) {
  const [genre, setGenre] = useState('amapiano');
  const [targetSeconds, setTargetSeconds] = useState(390);
  const [vocalMode, setVocalMode] = useState('place_once');
  const [working, setWorking] = useState(false);
  const job = project.extendJob;
  const mix = project.extendedMix;
  const hasStems = project.stems.length > 0;

  async function create() {
    setWorking(true);
    onError('');
    try {
      onProjectChange(await client.extendReconstruction(project.id, { genre, targetSeconds, vocalMode }));
    } catch (reason) {
      onError(reason.message);
    } finally {
      setWorking(false);
    }
  }

  const mixUrl = mix ? `${client.extendedMixUrl(project.id)}?v=${encodeURIComponent(job?.updatedAt ?? mix.durationSeconds ?? '')}` : '';

  return (
    <section className="rebuild-section extend-song">
      <header><div><p>Extend song</p><h2>6-7 min extended mix</h2></div><Clock size={20} /></header>
      <div className="extend-controls">
        <label>Genre
          <select value={genre} disabled={busy} onChange={(e) => setGenre(e.target.value)}>
            <option value="amapiano">Amapiano</option>
            <option value="deep_house">Deep House</option>
          </select>
        </label>
        <label>Length: {Math.floor(targetSeconds / 60)}:{String(targetSeconds % 60).padStart(2, '0')}
          <input type="range" min="360" max="420" step="10" value={targetSeconds}
                 disabled={busy} onChange={(e) => setTargetSeconds(Number(e.target.value))} />
        </label>
        <label>Vocals
          <select value={vocalMode} disabled={busy} onChange={(e) => setVocalMode(e.target.value)}>
            <option value="place_once">Place once</option>
            <option value="loop">Loop</option>
            <option value="drop">Instrumental</option>
          </select>
        </label>
        <button className="primary-button rebuild-inline" disabled={busy || working || !hasStems} onClick={create}>
          <Clock size={16} /> Create extended mix
        </button>
      </div>
      {job && job.status !== 'complete' && <progress max="100" value={job.progress}>{job.progress}%</progress>}
      {mix && (
        <div className="extend-result">
          <audio controls preload="metadata" src={mixUrl} />
          <a href={mixUrl} download>Download extended mix ({Math.round(mix.durationSeconds)}s)</a>
        </div>
      )}
    </section>
  );
}

function GuideCarousel({ project, client, busy, onProjectChange }) {
  const [index, setIndex] = useState(0);
  const steps = project.guideSteps;
  if (!steps.length) return null;
  const safeIndex = Math.min(index, steps.length - 1);
  const step = steps[safeIndex];
  return (
    <section className="guide-section">
      <header>
        <div><p>FL Studio 2025 guide</p><h2>{step.title}</h2></div>
        <span>{safeIndex + 1} / {steps.length}</span>
      </header>
      <div className="guide-layout">
        <div className="guide-image">
          <img src={step.imageAsset} alt={`${step.area}: ${step.action}`} />
          <span className="guide-hotspot" style={{ left: `${step.hotspot.x * 100}%`, top: `${step.hotspot.y * 100}%`, width: `${step.hotspot.width * 100}%`, height: `${step.hotspot.height * 100}%` }} />
        </div>
        <div className="guide-copy">
          <span className="guide-area">{step.area}</span>
          <p>{step.action}</p>
          <dl><dt>Menu path</dt><dd>{step.menuPath}</dd>{step.shortcut && <><dt>Shortcut</dt><dd>{step.shortcut}</dd></>}</dl>
          <strong>Expected: {step.expectedState}</strong>
          <div className="guide-controls">
            <button className="icon-button" aria-label="Previous guide step" disabled={safeIndex === 0} onClick={() => setIndex((value) => Math.max(0, value - 1))}><ChevronLeft size={18} /></button>
            <button className="primary-button" disabled={busy} onClick={async () => onProjectChange(await client.updateGuideStep(project.id, step.id, !step.completed))}>
              <Check size={17} /> {step.completed ? 'Completed' : 'Mark step complete'}
            </button>
            <button className="icon-button" aria-label="Next guide step" disabled={safeIndex === steps.length - 1} onClick={() => setIndex((value) => Math.min(steps.length - 1, value + 1))}><ChevronRight size={18} /></button>
          </div>
        </div>
      </div>
    </section>
  );
}

export default function ReconstructionWorkspace({ client = api }) {
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null);
  const [setup, setSetup] = useState(null);
  const [inventory, setInventory] = useState(null);
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inventoryItems = inventory?.items ?? [];
  const pluginCount = inventory?.plugins?.length ?? inventoryItems.filter((item) => item.kind === 'plugin').length;
  const sampleCount = inventory?.samples?.length ?? inventoryItems.filter((item) => item.kind === 'sample').length;

  useEffect(() => {
    let active = true;
    client.listReconstructions().then((items) => {
      if (!active) return;
      setProjects(items);
      setProject(items[0] ?? null);
    }).catch((reason) => active && setError(reason.message));
    client.analysisSetup().then((nextSetup) => {
      if (active) setSetup(nextSetup);
    }).catch((reason) => active && setError(reason.message));
    client.inventory().then((nextInventory) => {
      if (active) setInventory(nextInventory);
    }).catch((reason) => active && setError(reason.message));
    return () => { active = false; };
  }, [client]);

  useEffect(() => {
    const active = ['queued', 'running'];
    if (!project || !(active.includes(project.analysisJob?.status) || active.includes(project.extendJob?.status))) return undefined;
    const timer = window.setInterval(() => {
      client.getReconstruction(project.id).then(setProject).catch((reason) => setError(reason.message));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [client, project?.id, project?.analysisJob?.status, project?.extendJob?.status]);

  function adopt(next) {
    setProject(next);
    setProjects((items) => [next, ...items.filter((item) => item.id !== next.id)]);
  }

  async function run(task) {
    setBusy(true);
    setError('');
    try { await task(); } catch (reason) { setError(reason.message); } finally { setBusy(false); }
  }

  async function create(body) {
    await run(async () => adopt(await client.createReconstruction(body)));
  }

  async function upload() {
    await run(async () => {
      adopt(await client.uploadReconstructionStems(project.id, files));
      setFiles([]);
    });
  }

  async function removeProject() {
    await run(async () => {
      await client.deleteReconstruction(project.id);
      const remaining = projects.filter((item) => item.id !== project.id);
      setProjects(remaining);
      setProject(remaining[0] ?? null);
    });
  }

  return (
    <div className="rebuild-workspace">
      <header className="rebuild-topbar">
        <div><p>Audio-to-FL reconstruction</p><h1>Rebuild workspace</h1></div>
        <div className="rebuild-actions">
          {project && <StatusBadge status={project.status} />}
          {project && <button className="icon-button" aria-label="Export reconstruction ZIP" onClick={() => run(() => client.exportReconstruction(project.id))}><Download size={18} /></button>}
          {project && <button className="icon-button danger" aria-label="Delete reconstruction" onClick={removeProject}><Trash2 size={18} /></button>}
        </div>
      </header>
      <SetupBar setup={setup} busy={busy} onInstall={(approved) => run(async () => setSetup(await client.installAnalysisWorker(approved)))} />
      {error && <div className="rebuild-error">{error}</div>}
      {!project ? <ProjectCreator busy={busy} onCreate={create} /> : (
        <>
          <section className="project-selector">
            <div><p>Active reconstruction</p><h2>{project.title}</h2></div>
            <select aria-label="Active reconstruction" value={project.id} onChange={(event) => setProject(projects.find((item) => item.id === event.target.value))}>
              {projects.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
            </select>
            <button className="secondary-button rebuild-inline" onClick={() => setProject(null)}><Plus size={17} /> New project</button>
          </section>
          <UploadBand
            project={project}
            busy={busy}
            selectedFiles={files}
            onFiles={setFiles}
            onUpload={upload}
            onAnalyze={() => run(async () => adopt(await (project.status === 'error' ? client.retryReconstruction(project.id) : client.analyzeReconstruction(project.id))))}
          />
          <AnalysisHeader project={project} busy={busy} onCorrect={(values) => run(async () => adopt(await client.updateReconstruction(project.id, values)))} />
          <AcceptanceGate project={project} />
          <div className="rebuild-split">
            <EvidencePane project={project} client={client} busy={busy} onPatchPart={(partId, values) => run(async () => adopt(await client.updateReconstructionPart(project.id, partId, values)))} />
            <BlueprintPane project={project} client={client} busy={busy} onProjectChange={adopt} />
          </div>
          <Arrangement project={project} />
          <ExtendSong project={project} client={client} busy={busy} onError={setError} onProjectChange={adopt} />
          <SendToFl project={project} client={client} busy={busy} onError={setError} />
          <div className="rebuild-lower-grid">
            <Recommendations matches={project.soundMatches} busy={busy} onRefresh={() => run(async () => setInventory(await client.refreshInventory([])))} />
            <MixPlan plan={project.mixPlan} />
          </div>
          <GuideCarousel project={project} client={client} busy={busy} onProjectChange={adopt} />
          {inventory && <span className="inventory-footnote">Inventory indexed {pluginCount} plugins and {sampleCount} samples locally.</span>}
        </>
      )}
      {busy && <div className="rebuild-busy"><LoaderCircle size={18} className="spin" /> Working locally</div>}
    </div>
  );
}

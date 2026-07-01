import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import ReconstructionWorkspace from './ReconstructionWorkspace';

const setup = {
  ready: false,
  status: 'needs_action',
  message: 'Python 3.11 and FFmpeg are required.',
  checks: [],
};

function draftProject(overrides = {}) {
  return {
    id: 'project-1',
    title: 'Owned Suno session',
    rightsAccepted: true,
    status: 'draft',
    storageBytes: 0,
    stems: [],
    analysisJob: null,
    analysisSummary: null,
    parts: [],
    timeline: [],
    soundMatches: [],
    guideSteps: [],
    mixPlan: null,
    warnings: [],
    ...overrides,
  };
}

function clientFor(projects = []) {
  return {
    analysisSetup: vi.fn().mockResolvedValue(setup),
    listReconstructions: vi.fn().mockResolvedValue(projects),
    inventory: vi.fn().mockResolvedValue({ plugins: [], samples: [], scannedRoots: [] }),
    createReconstruction: vi.fn(),
    updateReconstruction: vi.fn(),
    uploadReconstructionStems: vi.fn(),
    getReconstruction: vi.fn(),
    updateReconstructionPart: vi.fn(),
    approveReconstructionPattern: vi.fn(),
    approveReconstructionAudio: vi.fn(),
    updateGuideStep: vi.fn(),
    analyzeReconstruction: vi.fn(),
    retryReconstruction: vi.fn(),
    installAnalysisWorker: vi.fn(),
    refreshInventory: vi.fn(),
    deleteReconstruction: vi.fn(),
    exportReconstruction: vi.fn(),
    exportReconstructionMidi: vi.fn(),
    syncReconstructionToFl: vi.fn().mockResolvedValue({
      connected: true,
      message: 'Synced FL session to the reconstruction.',
      tempo: { value: 112, status: 'applied' },
      channels: [{ index: 0, name: 'Bass', status: 'applied' }],
      mixer: [{ index: 1, name: 'Bass', status: 'applied' }],
      skipped: [],
    }),
    extendReconstruction: vi.fn().mockResolvedValue({}),
    extendedMixUrl: vi.fn().mockReturnValue('/api/reconstructions/project-1/extended-mix'),
  };
}

test('creates an ownership-confirmed project and uploads local stems', async () => {
  const created = draftProject();
  const uploaded = draftProject({
    status: 'uploaded',
    storageBytes: 48,
    stems: [{ id: 'stem-1', fileName: 'bass.wav', role: 'bass', sizeBytes: 48 }],
  });
  const client = clientFor();
  client.createReconstruction.mockResolvedValue(created);
  client.uploadReconstructionStems.mockResolvedValue(uploaded);

  render(<ReconstructionWorkspace client={client} />);

  await screen.findByRole('heading', { name: /start a reconstruction/i });
  fireEvent.change(screen.getByLabelText(/project title/i), { target: { value: 'Owned Suno session' } });
  fireEvent.click(screen.getByLabelText(/i own these stems/i));
  fireEvent.click(screen.getByRole('button', { name: /create project/i }));

  await screen.findByRole('heading', { name: 'Owned Suno session' });
  const file = new File(['RIFF....WAVE'], 'bass.wav', { type: 'audio/wav' });
  fireEvent.change(screen.getByLabelText(/stem files/i), { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: /upload 1 stem/i }));

  await screen.findByText('bass.wav');
  expect(client.createReconstruction).toHaveBeenCalledWith({
    title: 'Owned Suno session',
    rightsAccepted: true,
    genreProfile: 'south_african_dance',
  });
  expect(client.uploadReconstructionStems).toHaveBeenCalledWith('project-1', [file]);
});

test('requires consent before bootstrapping verified local analysis tools', async () => {
  const client = clientFor();
  client.analysisSetup.mockResolvedValue({
    ...setup,
    canInstall: true,
    bootstrapMethod: 'winget',
    installPlan: [
      { id: 'Python.Python.3.11', name: 'Python 3.11', publisher: 'Python Software Foundation', source: 'winget' },
      { id: 'Gyan.FFmpeg', name: 'FFmpeg Windows build', publisher: 'Gyan', source: 'winget' },
    ],
  });
  client.installAnalysisWorker.mockResolvedValue({ ready: true, status: 'ready', checks: [] });

  render(<ReconstructionWorkspace client={client} />);

  await screen.findByRole('heading', { name: /start a reconstruction/i });
  const install = screen.getByRole('button', { name: /install prerequisites and worker/i });
  expect(install).toBeDisabled();
  expect(screen.getByText(/python software foundation/i)).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText(/approve winget and local worker installation/i));
  expect(install).toBeEnabled();
  fireEvent.click(install);

  await waitFor(() => expect(client.installAnalysisWorker).toHaveBeenCalledWith(true));
  expect(await screen.findByText(/local analysis worker ready/i)).toBeInTheDocument();
});

test('shows analysis evidence and supports overrides, approval, recommendations, and guide completion', async () => {
  const pattern = {
    id: 'pattern-1',
    name: 'Bass bars 1-8',
    startBar: 1,
    bars: 8,
    placements: [1],
    payload: {
      status: 'draft',
      bars: 8,
      bpm: 114,
      key: 'G',
      scale: 'minor',
      notes: [{ pitch: 43, startBeats: 0, durationBeats: 1, velocity: 0.9 }],
    },
  };
  const part = {
    id: 'part-1',
    name: 'Bass',
    role: 'bass',
    outputMode: 'midi',
    confidence: 0.74,
    requiresReview: true,
    instrumentHint: 'BooBass or 3xOsc',
    patterns: [pattern],
    approved: false,
    warnings: [],
  };
  const guide = {
    id: 'guide-1',
    order: 1,
    title: 'Open the Channel Rack',
    area: 'Channel Rack',
    action: 'Open the instrument and pattern list.',
    menuPath: 'View > Channel rack',
    shortcut: 'F6',
    imageAsset: '/guides/fl-2025/channel-rack.png',
    hotspot: { x: 0.08, y: 0.08, width: 0.18, height: 0.12 },
    expectedState: 'The Channel Rack is visible.',
    completed: false,
  };
  const project = draftProject({
    status: 'review',
    analysisJob: { status: 'running', progress: 64, stage: 'transcription', message: 'Tracing bass notes.' },
    analysisSummary: { bpm: 114, key: 'G', scale: 'minor', durationSeconds: 180, bpmConfidence: 0.94, keyConfidence: 0.82 },
    parts: [part],
    timeline: [{ id: 'section-1', name: 'Groove', startBar: 1, bars: 16, activePartIds: ['part-1'] }],
    soundMatches: [{ id: 'sound-1', name: 'BooBass', installed: true, score: 0.91, source: 'inventory', reason: 'Installed bass instrument.' }],
    guideSteps: [guide],
    mixPlan: { steps: [{ order: 1, targetLabel: 'Bass', plugin: 'Fruity Parametric EQ 2', action: 'Remove unused lows.' }] },
  });
  const audioOverride = { ...project, parts: [{ ...part, outputMode: 'audio' }] };
  const approved = {
    ...project,
    parts: [{ ...part, patterns: [{ ...pattern, payload: { ...pattern.payload, status: 'approved' } }] }],
  };
  const guideDone = { ...project, guideSteps: [{ ...guide, completed: true }] };
  const client = clientFor([project]);
  client.getReconstruction.mockResolvedValue(project);
  client.updateReconstructionPart.mockImplementation((_projectId, _partId, body) => Promise.resolve({
    ...audioOverride,
    parts: [{ ...part, ...body }],
  }));
  client.approveReconstructionPattern.mockResolvedValue({ project: approved, payload: pattern.payload });
  client.updateGuideStep.mockResolvedValue(guideDone);

  render(<ReconstructionWorkspace client={client} />);

  expect(await screen.findByRole('progressbar')).toHaveValue(64);
  expect(screen.getByText(/review required/i)).toBeInTheDocument();
  expect(screen.getByText('BooBass')).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText(/output mode for bass/i), { target: { value: 'audio' } });
  await waitFor(() => expect(client.updateReconstructionPart).toHaveBeenCalledWith('project-1', 'part-1', { outputMode: 'audio' }));

  fireEvent.change(screen.getByLabelText(/role for bass/i), { target: { value: 'log_drum' } });
  await waitFor(() => expect(client.updateReconstructionPart).toHaveBeenCalledWith('project-1', 'part-1', { role: 'log_drum' }));

  fireEvent.change(screen.getByLabelText(/sound for bass/i), { target: { value: 'sound-1' } });
  await waitFor(() => expect(client.updateReconstructionPart).toHaveBeenCalledWith('project-1', 'part-1', { selectedSoundId: 'sound-1' }));

  fireEvent.click(screen.getByRole('button', { name: /approve bass bars 1-8/i }));
  await waitFor(() => expect(client.approveReconstructionPattern).toHaveBeenCalledWith('project-1', 'part-1', 'pattern-1'));

  fireEvent.click(screen.getByRole('button', { name: /mark step complete/i }));
  await waitFor(() => expect(client.updateGuideStep).toHaveBeenCalledWith('project-1', 'guide-1', true));
});

test('sends the rebuild to FL via MIDI download and bridge sync', async () => {
  const project = draftProject({
    status: 'review',
    parts: [
      {
        id: 'part-1', sourceStemId: 'stem-1', name: 'Bass', role: 'bass',
        outputMode: 'midi', confidence: 0.9, requiresReview: false, instrumentHint: 'BooBass',
        patterns: [], audioRelativePath: null, audioStartSeconds: 0,
        selectedSoundId: null, warnings: [], approved: false,
      },
    ],
  });
  const client = clientFor([project]);

  render(<ReconstructionWorkspace client={client} />);

  const download = await screen.findByRole('button', { name: /Download arrangement MIDI/i });
  fireEvent.click(download);
  expect(client.exportReconstructionMidi).toHaveBeenCalledWith('project-1');

  fireEvent.click(screen.getByRole('button', { name: /Sync FL to this rebuild/i }));
  await waitFor(() => expect(client.syncReconstructionToFl).toHaveBeenCalledWith('project-1'));
  expect(await screen.findByText(/1 channel named/i)).toBeInTheDocument();
});

test('summarizes reconstruction acceptance blockers before final handoff', async () => {
  const pattern = {
    id: 'pattern-1',
    name: 'Bass bars 1-8',
    startBar: 1,
    bars: 8,
    placements: [1],
    payload: {
      status: 'approved',
      bars: 8,
      bpm: 114,
      key: 'F',
      scale: 'minor',
      notes: [{ pitch: 43, startBeats: 0, durationBeats: 1, velocity: 0.9 }],
    },
  };
  const part = {
    id: 'part-1',
    name: 'Bass',
    role: 'bass',
    outputMode: 'midi',
    confidence: 0.76,
    requiresReview: true,
    instrumentHint: 'BooBass or FLEX bass',
    patterns: [pattern],
    selectedSoundId: null,
    approved: true,
    warnings: [],
  };
  const secondPart = {
    ...part,
    id: 'part-2',
    name: 'Synth',
    role: 'melody',
    instrumentHint: 'FLEX lead',
  };
  const guide = {
    id: 'guide-1',
    order: 1,
    title: 'Apply the MIDI pattern',
    area: 'Piano Roll',
    action: 'Open the selected channel Piano Roll and apply the approved pattern.',
    menuPath: 'Tools > Scripts > FL Connector Apply Payload',
    shortcut: null,
    imageAsset: '/guides/fl-2025/apply-payload.png',
    hotspot: { x: 0.08, y: 0.08, width: 0.18, height: 0.12 },
    expectedState: 'Notes appear in the Piano Roll.',
    completed: false,
  };
  const project = draftProject({
    status: 'review',
    analysisSummary: { bpm: 117.45, key: 'F', scale: 'minor', durationSeconds: 214, bpmConfidence: 0.98, keyConfidence: 0.65 },
    parts: [part, secondPart],
    soundMatches: [{ id: 'sound-1', name: 'BooBass', installed: true, score: 0.91, source: 'inventory', reason: 'Installed bass instrument.' }],
    guideSteps: [guide],
  });
  const client = clientFor([project]);

  render(<ReconstructionWorkspace client={client} />);

  expect(await screen.findByRole('heading', { name: /acceptance gate/i })).toBeInTheDocument();
  expect(screen.getByText(/2\/2 parts approved/i)).toBeInTheDocument();
  expect(screen.getByText(/2 MIDI parts need sounds/i)).toBeInTheDocument();
  expect(screen.getByText(/0\/1 guide steps complete/i)).toBeInTheDocument();
  expect(screen.getByText(/Key confidence 65%/i)).toBeInTheDocument();
});

test('starts an extended mix from the Extend Song card', async () => {
  const project = draftProject({
    status: 'review',
    stems: [{ id: 's1', fileName: 'drums.wav', storedName: 'drums.wav', relativePath: 'input/drums.wav',
              mediaType: 'audio/wav', sizeBytes: 1000, sha256: 'x'.repeat(64), role: 'drums',
              status: 'uploaded', createdAt: 'now' }],
  });
  const client = clientFor([project]);

  render(<ReconstructionWorkspace client={client} />);

  const create = await screen.findByRole('button', { name: /Create extended mix/i });
  fireEvent.click(create);
  await waitFor(() => expect(client.extendReconstruction).toHaveBeenCalledWith(
    'project-1', expect.objectContaining({ genre: expect.any(String), vocalMode: expect.any(String) })));
});

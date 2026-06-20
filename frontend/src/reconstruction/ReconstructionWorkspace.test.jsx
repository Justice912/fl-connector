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
  client.updateReconstructionPart.mockResolvedValue(audioOverride);
  client.approveReconstructionPattern.mockResolvedValue(approved);
  client.updateGuideStep.mockResolvedValue(guideDone);

  render(<ReconstructionWorkspace client={client} />);

  expect(await screen.findByRole('progressbar')).toHaveValue(64);
  expect(screen.getByText(/review required/i)).toBeInTheDocument();
  expect(screen.getByText('BooBass')).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText(/output mode for bass/i), { target: { value: 'audio' } });
  await waitFor(() => expect(client.updateReconstructionPart).toHaveBeenCalledWith('project-1', 'part-1', { outputMode: 'audio' }));

  fireEvent.click(screen.getByRole('button', { name: /approve bass bars 1-8/i }));
  await waitFor(() => expect(client.approveReconstructionPattern).toHaveBeenCalledWith('project-1', 'part-1', 'pattern-1'));

  fireEvent.click(screen.getByRole('button', { name: /mark step complete/i }));
  await waitFor(() => expect(client.updateGuideStep).toHaveBeenCalledWith('project-1', 'guide-1', true));
});

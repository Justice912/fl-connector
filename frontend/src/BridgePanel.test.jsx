import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { BridgePanel, BridgeTrackControls } from './App';

test('track controls fire select/mute/solo with the track index', () => {
  const onSelectTrack = vi.fn();
  const onMuteTrack = vi.fn();
  const onSoloTrack = vi.fn();
  const track = { index: 2, name: 'Bass', volume: 0.7, pan: 0.5, selected: false, slots: [] };
  render(
    <BridgeTrackControls
      track={track}
      busy={false}
      onSetMixerTrack={() => {}}
      onSelectTrack={onSelectTrack}
      onMuteTrack={onMuteTrack}
      onSoloTrack={onSoloTrack}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /^select$/i }));
  fireEvent.click(screen.getByRole('button', { name: /^mute$/i }));
  fireEvent.click(screen.getByRole('button', { name: /^solo$/i }));
  expect(onSelectTrack).toHaveBeenCalledWith(2);
  expect(onMuteTrack).toHaveBeenCalledWith(2);
  expect(onSoloTrack).toHaveBeenCalledWith(2);
});

test('track controls Apply sends only changed name', () => {
  const onSetMixerTrack = vi.fn();
  const track = { index: 1, name: 'Keys', volume: 0.7, pan: 0.5, selected: false, slots: [] };
  render(
    <BridgeTrackControls
      track={track}
      busy={false}
      onSetMixerTrack={onSetMixerTrack}
      onSelectTrack={() => {}}
      onMuteTrack={() => {}}
      onSoloTrack={() => {}}
    />,
  );
  fireEvent.change(screen.getByLabelText(/track 1 name/i), { target: { value: 'Lead Keys' } });
  fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));
  expect(onSetMixerTrack).toHaveBeenCalledWith(1, { name: 'Lead Keys' });
});

test('sync tempo button sends the song bpm', () => {
  const onSetTempo = vi.fn();
  const bridge = {
    status: 'connected', message: 'ok',
    transport: { playing: false, tempo: 120 }, tracks: [], setup: [], errors: [],
  };
  render(
    <BridgePanel
      bridge={bridge}
      setupPlan={{ status: 'ready', checks: [], manualSteps: [] }}
      busy={false}
      songBpm={120}
      onRefresh={() => {}}
      onRefreshSetup={() => {}}
      onInstallScripts={() => {}}
      onTransportAction={() => {}}
      onSetTempo={onSetTempo}
      onSetMixerTrack={() => {}}
      onSelectTrack={() => {}}
      onMuteTrack={() => {}}
      onSoloTrack={() => {}}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /sync tempo/i }));
  expect(onSetTempo).toHaveBeenCalledWith(120);
});

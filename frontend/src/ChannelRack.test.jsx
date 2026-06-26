import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { BridgeChannelControls, BridgePanel } from './App';

test('channel controls fire select/mute/solo with the channel index', () => {
  const onSelectChannel = vi.fn();
  const onMuteChannel = vi.fn();
  const onSoloChannel = vi.fn();
  const channel = { index: 2, name: 'Snare', volume: 0.7, pan: -0.1, muted: false, solo: false, selected: false };
  render(
    <BridgeChannelControls
      channel={channel}
      busy={false}
      onSetChannel={() => {}}
      onSelectChannel={onSelectChannel}
      onMuteChannel={onMuteChannel}
      onSoloChannel={onSoloChannel}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /^select$/i }));
  fireEvent.click(screen.getByRole('button', { name: /^mute$/i }));
  fireEvent.click(screen.getByRole('button', { name: /^solo$/i }));
  expect(onSelectChannel).toHaveBeenCalledWith(2);
  expect(onMuteChannel).toHaveBeenCalledWith(2);
  expect(onSoloChannel).toHaveBeenCalledWith(2);
});

test('channel Apply sends only the changed name', () => {
  const onSetChannel = vi.fn();
  const channel = { index: 1, name: 'Kick', volume: 0.8, pan: 0.0, muted: false, solo: false, selected: false };
  render(
    <BridgeChannelControls
      channel={channel}
      busy={false}
      onSetChannel={onSetChannel}
      onSelectChannel={() => {}}
      onMuteChannel={() => {}}
      onSoloChannel={() => {}}
    />,
  );
  fireEvent.change(screen.getByLabelText(/channel 1 name/i), { target: { value: '808 Kick' } });
  fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));
  expect(onSetChannel).toHaveBeenCalledWith(1, { name: '808 Kick' });
});

test('bridge panel renders a channel rack row from snapshot channels', () => {
  const bridge = {
    status: 'connected', message: 'ok',
    transport: { playing: false, tempo: 120 },
    tracks: [],
    channels: [{ index: 0, name: 'Kick', volume: 0.8, pan: 0.0, muted: false, solo: false, selected: false }],
    setup: [], errors: [],
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
      onSetTempo={() => {}}
      onSetMixerTrack={() => {}}
      onSelectTrack={() => {}}
      onMuteTrack={() => {}}
      onSoloTrack={() => {}}
      onSetChannel={() => {}}
      onSelectChannel={() => {}}
      onMuteChannel={() => {}}
      onSoloChannel={() => {}}
    />,
  );
  expect(screen.getByLabelText(/channel 0 name/i)).toBeInTheDocument();
});

import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { SongDraftPanel } from './App';

function sampleSong() {
  return {
    id: 'song-1',
    title: 'Amapiano full draft',
    parts: [
      {
        id: 'p1',
        applyOrder: 1,
        patternName: 'FPC bounce drums',
        pluginHint: 'FPC',
        payload: { id: 'pay1', notes: [] },
      },
    ],
    arrangement: [{ name: 'Intro', startBar: 1, bars: 2, activeParts: ['drums'] }],
  };
}

test('song panel triggers a full-song MIDI export', () => {
  const onExportSong = vi.fn();
  render(
    <SongDraftPanel
      song={sampleSong()}
      selectedPartId=""
      onSelectPart={() => {}}
      onExportSong={onExportSong}
      onExportPart={() => {}}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /download song midi/i }));
  expect(onExportSong).toHaveBeenCalledTimes(1);
});

test('song panel triggers a per-part MIDI export', () => {
  const onExportPart = vi.fn();
  render(
    <SongDraftPanel
      song={sampleSong()}
      selectedPartId=""
      onSelectPart={() => {}}
      onExportSong={() => {}}
      onExportPart={onExportPart}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /download fpc bounce drums midi/i }));
  expect(onExportPart).toHaveBeenCalledTimes(1);
});

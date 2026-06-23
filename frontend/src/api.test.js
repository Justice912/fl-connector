import { describe, expect, test } from 'vitest';

import { normalizeApiBase } from './api';

describe('normalizeApiBase', () => {
  test('keeps an empty API base for the local Vite proxy', () => {
    expect(normalizeApiBase(undefined)).toBe('');
    expect(normalizeApiBase('   ')).toBe('');
  });

  test('trims whitespace and trailing slashes from configured API bases', () => {
    expect(normalizeApiBase(' http://127.0.0.1:8765/// ')).toBe('http://127.0.0.1:8765');
  });
});

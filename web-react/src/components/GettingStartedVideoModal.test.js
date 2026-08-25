import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import GettingStartedVideoModal from './GettingStartedVideoModal';

describe('GettingStartedVideoModal', () => {
  test('renders the privacy-enhanced player without autoplay', () => {
    render(<GettingStartedVideoModal UITheme="dark" onClose={() => {}} />);

    const player = screen.getByTitle('TradeWave Getting Started video');
    expect(player).toHaveAttribute('src', expect.stringContaining('youtube-nocookie.com/embed/7ZQoj2e93oo'));
    expect(player.getAttribute('src')).not.toContain('autoplay=1');
  });

  test('closes from the primary action', () => {
    const onClose = jest.fn();
    render(<GettingStartedVideoModal UITheme="light" onClose={onClose} />);

    fireEvent.click(screen.getByRole('button', { name: 'Start Exploring' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

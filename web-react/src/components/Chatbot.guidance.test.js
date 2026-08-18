import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import Chatbot from './Chatbot';
import { UserContext } from './UserContext';

jest.mock('./SeasonalPatternsPopup', () => () => null);

const serverTurn = {
  reply: '<b>AAPL</b> historical evidence request.',
  actions: [{
    type: 'set_view',
    spec: {
      market: '2',
      symbol: 'AAPL',
      entry_date: '2026-08-17',
      days_out: 30,
    },
  }],
  suggestions: [{
    label: 'Judge reliability',
    prompt: "How reliable is AAPL's current seasonal pattern?",
  }],
  turn_id: 'turn-1',
};

const baseProps = {
  UITheme: 'light',
  symbol: 'AAPL',
  startDate: '2026-08-17',
  daysOut: 30,
  seasonalYears: 10,
  PEselected: 'cons',
  trimYear: 0,
  selectedSecurity: 'S&P 500 STOCKS',
  securityTypeList: [{ id: '2', value: 'S&P 500 STOCKS' }],
  viewerDataState: { status: 'idle', request_key: '' },
  opportunities: [],
  oppTableLength: 0,
  oppTableYears: 10,
  tradeDetailData: {},
  seasonalBarChartData: [],
  resourceObj: [],
};

const renderTara = (beginAction) => {
  const props = { ...baseProps, BeginTaraViewAction: beginAction };
  const view = render(
    <UserContext.Provider value={{ token: 'test-token', resourceObj: [] }}>
      <Chatbot {...props} />
    </UserContext.Provider>,
  );
  return {
    ...view,
    rerenderWithAction: (taraActionState) => view.rerender(
      <UserContext.Provider value={{ token: 'test-token', resourceObj: [] }}>
        <Chatbot {...props} taraActionState={taraActionState} />
      </UserContext.Provider>,
    ),
  };
};

beforeEach(() => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => serverTurn,
  });
});
afterEach(() => {
  jest.restoreAllMocks();
});

test('reveals server guidance only after the requested graph is verified', async () => {
  const beginAction = jest.fn().mockReturnValue({
    ok: true,
    transaction: {
      action_ids: ['action-1'],
      action_proofs: [],
      request_key: 'requested-view',
    },
  });
  const view = renderTara(beginAction);

  fireEvent.click(screen.getByTitle("Analyze AAPL's current seasonal pattern"));
  await waitFor(() => expect(beginAction).toHaveBeenCalledTimes(1));

  expect(screen.queryByText('Judge reliability')).not.toBeInTheDocument();
  expect(screen.getByText('Tara is thinking...')).toBeInTheDocument();

  view.rerenderWithAction({
    action_ids: ['action-1'],
    status: 'succeeded',
    requested_spec: serverTurn.actions[0].spec,
    target: { symbol: 'AAPL' },
    requires_chart_data: true,
    observed_view: serverTurn.actions[0].spec,
    data_points: 20,
  });

  expect(await screen.findByText('Judge reliability')).toBeInTheDocument();
  expect(screen.getByText(/pattern and seasonal graph loaded/i)).toBeInTheDocument();
});

test('a failed graph load offers retry guidance instead of advancing', async () => {
  const beginAction = jest.fn().mockReturnValue({
    ok: true,
    transaction: {
      action_ids: ['action-2'],
      action_proofs: [],
      request_key: 'requested-view',
    },
  });
  const view = renderTara(beginAction);

  fireEvent.click(screen.getByTitle("Analyze AAPL's current seasonal pattern"));
  await waitFor(() => expect(beginAction).toHaveBeenCalledTimes(1));

  view.rerenderWithAction({
    action_ids: ['action-2'],
    status: 'failed',
    reason: 'chart_load_timeout',
    requested_spec: serverTurn.actions[0].spec,
    target: { symbol: 'AAPL' },
    requires_chart_data: true,
    data_points: 0,
  });

  expect(await screen.findByText('Try the question again')).toBeInTheDocument();
  expect(screen.queryByText('Judge reliability')).not.toBeInTheDocument();
  expect(screen.getByText(/I have not marked it as loaded/i)).toBeInTheDocument();
});

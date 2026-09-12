import { useEffect, useState } from 'react';
import { appserverURL } from './Common';
import { twFetch } from './twFetch';
import { acceptEngineProjection } from './engineProjection';

export default function useEngineProjection(expected, token, enabled) {
    const key = JSON.stringify(expected);
    const [state, setState] = useState({ key: '', result: null, status: 'idle' });
    useEffect(() => {
        if (!enabled || !token) return undefined;
        let stale = false;
        const e = JSON.parse(key);
        setState({ key, result: null, status: 'loading' });
        const path = [e.market, e.entry_date, e.symbol, Number(e.days_out) - 1, e.years]
            .map(encodeURIComponent).join('/');
        const query = new URLSearchParams({ token, exact_window: '1', price_date: e.price_date,
            period_days: String(e.period_days), timeframe: e.timeframe });
        twFetch(`${appserverURL()}/SeasonalProjection/${path}?${query}`)
            .then(response => response.ok ? response.json() : null)
            .then(payload => {
                if (stale) return;
                const result = acceptEngineProjection(payload, e);
                setState({ key, result, status: result ? 'ready' : 'unavailable' });
            })
            .catch(() => { if (!stale) setState({ key, result: null, status: 'unavailable' }); });
        return () => { stale = true; };
    }, [key, token, enabled]);
    return enabled && state.key === key ? state : { result: null, status: enabled ? 'loading' : 'idle' };
}

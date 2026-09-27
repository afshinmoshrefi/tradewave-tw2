import React, { useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom';
import { appserverURL, statusColor } from './Common';
import { twFetch } from './twFetch';
import { parseHoldings, repeatedTickers, selectScenarioRows } from './portfolioScenarioUtils';
import './styles/PortfolioScenarios.css';

const HORIZONS = [{ key: '30', label: '30 days' }, { key: '60', label: '60 days' }, { key: '90', label: '90 days' }, { key: 'eoy', label: 'End of year' }, { key: 'custom', label: 'Custom' }];
const colors = ['Unmarked', 'Black', 'Red', 'Green', 'Gold', 'Blue'];
const money = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(Number(value)) : 'Unavailable';
const percent = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)}%` : 'Unavailable';
const date = value => value ? new Date(/^\d{4}-\d{2}-\d{2}$/.test(String(value)) ? `${value}T12:00:00` : value).toLocaleString(undefined, { dateStyle: 'medium', ...(String(value).includes('T') ? { timeStyle: 'short' } : {}) }) : 'Unavailable';
const csvCell = value => `"${String(value == null ? '' : value).replace(/"/g, '""')}"`;

function downloadCsv(report) {
  const header = ['Record type', 'Report', 'Created', 'Horizon', 'Start', 'End', 'Year', 'Symbol', 'Shares', 'Direction', 'Price', 'Price date', 'Base value', 'End value', 'Change', 'Change %', 'Evidence'];
  const lines = [header];
  const sources = Object.fromEntries((report.holdings || []).map(item => [item.dr_id, item]));
  (report.horizons || []).forEach(horizon => {
    (horizon.holdings || []).forEach(holding => {
      const source = sources[holding.dr_id] || {};
      lines.push(['Holding average', report.title, report.created_at, horizon.key, horizon.start_date, horizon.end_date, '', holding.symbol, source.shares, source.direction, source.price, source.price_date, holding.base_value, holding.mean_end_value, holding.mean_change, holding.mean_return_pct, holding.count == null ? '' : `${holding.count} common years`]);
    });
    (horizon.annual_outcomes || []).forEach(outcome => {
      lines.push(['Annual portfolio', report.title, report.created_at, horizon.key, horizon.start_date, horizon.end_date, outcome.year, '', '', '', '', '', horizon.base_value, outcome.end_value, outcome.change, outcome.change_pct, 'Common completed year']);
      (outcome.contributions || []).forEach(contribution => {
        const source = sources[contribution.dr_id] || {};
        lines.push(['Annual holding', report.title, report.created_at, horizon.key, horizon.start_date, horizon.end_date, outcome.year, contribution.symbol, source.shares, source.direction, source.price, source.price_date, source.base_value, '', contribution.change, contribution.return_pct, 'Historical contribution']);
      });
    });
  });
  const blob = new Blob([lines.map(line => line.map(csvCell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = `tradewave-scenario-${report.id}.csv`; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function Bars({ outcomes, labelKey = 'year', mean, median }) {
  const usable = (outcomes || []).filter(item => item.change != null && Number.isFinite(Number(item.change)));
  if (!usable.length) return <p className="ps-muted">Annual outcomes are unavailable for this horizon.</p>;
  const max = Math.max(1, ...usable.map(item => Math.abs(Number(item.change))), ...[mean, median].filter(value => value != null).map(value => Math.abs(Number(value))));
  return <div className="ps-bars" role="img" aria-label="Historical annual portfolio gain and loss">
    {usable.map((item, index) => <div className="ps-bar-row" key={`${item[labelKey]}-${index}`}>
      <span>{item[labelKey]}</span><div className="ps-bar-track"><i className={Number(item.change) >= 0 ? 'positive' : 'negative'} style={{ left: `${50 + Math.min(0, Number(item.change) / max * 50)}%`, width: `${Math.abs(Number(item.change)) / max * 50}%` }} />{mean != null && <b className="ps-mean-marker" style={{ left: `${50 + Number(mean) / max * 50}%` }} />}{median != null && <b className="ps-median-marker" style={{ left: `${50 + Number(median) / max * 50}%` }} />}</div><strong className={Number(item.change) >= 0 ? 'ps-up' : 'ps-down'}>{money(item.change)}</strong>
    </div>)}
  </div>;
}

export default function PortfolioScenarios({ portfolioId, portfolioName, holdings, resourceObj, token, onClose, onImport, initialTab = 'create' }) {
  const [tab, setTab] = useState(initialTab);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [rawImport, setRawImport] = useState('');
  const [preview, setPreview] = useState(null);
  const [duplicateApproved, setDuplicateApproved] = useState(false);
  const [statuses, setStatuses] = useState([]);
  const [shares, setShares] = useState({});
  const [directions, setDirections] = useState({});
  const [title, setTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [horizons, setHorizons] = useState(['30', '60', '90', 'eoy']);
  const [customDays, setCustomDays] = useState('120');
  const [years, setYears] = useState('10');
  const [reports, setReports] = useState([]);
  const [report, setReport] = useState(null);
  const [revision, setRevision] = useState(null);
  const [sort, setSort] = useState('symbol');
  const [selectedHorizon, setSelectedHorizon] = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteAcknowledged, setDeleteAcknowledged] = useState(false);
  const [editMeta, setEditMeta] = useState(false);

  const api = async (path, options = {}) => {
    const response = await twFetch(`${appserverURL()}${path}${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`, {
      ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(String(result.error || result.message || `Request failed (${response.status}).`).replace(/_/g, ' '));
    return result;
  };
  const basePath = `/portfolio_scenarios/${encodeURIComponent(portfolioId)}`;
  const selected = useMemo(() => revision ? (revision.holdings || []) : selectScenarioRows(holdings || [], statuses), [revision, holdings, statuses]);
  const repeats = useMemo(() => repeatedTickers(selected), [selected]);
  const importRepeats = useMemo(() => repeatedTickers((preview || []).filter(row => row.status === 'ready')), [preview]);
  const selectedReportHorizon = (report?.horizons || []).find(item => item.key === selectedHorizon) || report?.horizons?.[0];
  const frozenById = Object.fromEntries((report?.holdings || []).map(item => [item.dr_id, item]));

  useEffect(() => {
    const onKey = event => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    document.body.classList.add('ps-open');
    return () => { window.removeEventListener('keydown', onKey); document.body.classList.remove('ps-open', 'ps-print'); };
  }, [onClose]);
  useEffect(() => { if (tab === 'history') loadReports(); }, [tab, portfolioId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!report || report.status !== 'running') return undefined;
    const timer = setInterval(() => openReport(report.id, false), 5000);
    return () => clearInterval(timer);
  }, [report?.id, report?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const cleanup = () => document.body.classList.remove('ps-print');
    window.addEventListener('afterprint', cleanup);
    return () => window.removeEventListener('afterprint', cleanup);
  }, []);

  const loadReports = async () => {
    try { const result = await api(basePath); setReports(result.reports || []); }
    catch (e) { setError(e.message); }
  };
  const openReport = async (id, show = true) => {
    try {
      const result = await api(`${basePath}/${encodeURIComponent(id)}`);
      setReport(result.report);
      if (show) { setSelectedHorizon(result.report.horizons?.[0]?.key || ''); setTab('report'); setError(''); }
    } catch (e) { setError(e.message); }
  };
  const showTab = next => { setError(''); setTab(next); };

  const previewImport = async () => {
    const parsed = parseHoldings(rawImport);
    if (parsed.errors.length) { setError(parsed.errors.join(' ')); setPreview(null); return; }
    setBusy(true); setError('');
    try { const result = await api('/portfolio_holdings/preview', { method: 'POST', body: JSON.stringify({ rows: parsed.rows }) }); setPreview(result.rows || []); setDuplicateApproved(false); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const updateImportMatch = async (index, resourceID) => {
    setBusy(true); setError('');
    try {
      const input = preview.map(row => ({ symbol: row.symbol, shares: row.shares, ...(String(row.index) === String(index) ? resourceID ? { resourceID } : {} : row.resourceID ? { resourceID: row.resourceID } : {}) }));
      const result = await api('/portfolio_holdings/preview', { method: 'POST', body: JSON.stringify({ rows: input }) });
      setPreview(result.rows || []);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const saveImport = async () => {
    if (!preview?.length || preview.some(row => row.status !== 'ready' || !String(row.resourceID || '').length)) { setError('Resolve every row before importing. Unsupported or unmatched rows must be corrected in the source.'); return; }
    if (importRepeats.length && !duplicateApproved) { setError('Confirm repeated tickers before importing. Each row creates a separate holding.'); return; }
    setBusy(true); setError('');
    try {
      await api(`/portfolio_holdings/${encodeURIComponent(portfolioId)}`, { method: 'POST', body: JSON.stringify({ rows: preview.map(row => ({ symbol: row.symbol, shares: row.shares, resourceID: row.resourceID })) }) });
      setPreview(null); setRawImport(''); onImport(); showTab('create');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const startRevision = source => {
    setRevision(source); setTitle(`${source.title} - revision`); setNotes(source.notes || '');
    setHorizons(source.settings?.horizons || ['30', '60', '90', 'eoy']);
    setCustomDays(String(source.settings?.custom_days || 120)); setYears(source.settings?.years || '10');
    setShares(Object.fromEntries((source.holdings || []).map(row => [row.dr_id, row.shares])));
    setDirections(Object.fromEntries((source.holdings || []).map(row => [row.dr_id, row.direction])));
    setStatuses([]); showTab('create');
  };
  const createScenario = async () => {
    if (!selected.length) { setError('Select at least one holding with positive shares.'); return; }
    if (!horizons.length) { setError('Choose at least one horizon.'); return; }
    if (horizons.includes('custom') && (!/^\d+$/.test(customDays) || +customDays < 1 || +customDays > 366)) { setError('Custom horizon must be 1 to 366 calendar days.'); return; }
    if (selected.some(row => !Number.isFinite(Number(shares[row.dr_id] ?? row.shares ?? row.num_shares)) || Number(shares[row.dr_id] ?? row.shares ?? row.num_shares) <= 0)) { setError('Every included holding needs positive shares.'); return; }
    setBusy(true); setError('');
    try {
      const frozen = selected.map(row => ({ dr_id: row.dr_id, resourceID: row.resourceID, symbol: row.symbol, shares: Number(shares[row.dr_id] ?? row.shares ?? row.num_shares), direction: directions[row.dr_id] || row.direction || 'long', status: String(row.status || '0') }));
      const payload = { title: title.trim() || undefined, notes: notes.trim(), ...(revision ? { parent_id: revision.id, holdings: frozen } : { selection: { row_ids: selected.map(row => row.dr_id) }, shares: Object.fromEntries(frozen.map(row => [row.dr_id, row.shares])), directions: Object.fromEntries(frozen.map(row => [row.dr_id, row.direction])) }), settings: { horizons, years, ...(horizons.includes('custom') ? { custom_days: Number(customDays) } : {}) } };
      const result = await api(basePath, { method: 'POST', body: JSON.stringify(payload) });
      setRevision(null); setReport(result.report); setSelectedHorizon(result.report?.horizons?.[0]?.key || ''); setTab('report');
      loadReports();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const updateMetadata = async () => {
    setBusy(true); setError('');
    try { const result = await api(`${basePath}/${encodeURIComponent(report.id)}`, { method: 'PATCH', body: JSON.stringify({ title: title.trim(), notes: notes.trim() }) }); setReport(result.report); setEditMeta(false); loadReports(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const deleteReport = async () => {
    if (!deleteAcknowledged || !deleteTarget) return;
    setBusy(true); setError('');
    try { await api(`${basePath}/${encodeURIComponent(deleteTarget.id)}`, { method: 'DELETE', body: JSON.stringify({ confirm_forever: true }) }); setDeleteTarget(null); setDeleteAcknowledged(false); setReport(null); setTab('history'); loadReports(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const printReport = () => { document.body.classList.add('ps-print'); window.print(); };

  return ReactDOM.createPortal(<div className="ps-overlay" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="ps-shell" role="dialog" aria-modal="true" aria-label="Portfolio Scenario Studio">
      <header className="ps-topbar"><div className="ps-mark">TW<span> / </span>RESEARCH</div><div className="ps-top-actions"><span className="ps-private">Private workspace</span><button className="ps-close" onClick={onClose} aria-label="Close Scenario Studio">×</button></div></header>
      <div className="ps-heading"><div><p className="ps-kicker">PORTFOLIO / {portfolioName || 'SELECTED'}</p><h1>Scenario Studio<span className="ps-title-dot">.</span></h1><p>Explore fixed-share positions against TradeWave's historical windows.</p></div><div className="ps-heading-accent" aria-hidden="true"><span>01</span><i /></div></div>
      <nav className="ps-tabs" aria-label="Scenario Studio sections"><button className={tab === 'import' ? 'active' : ''} onClick={() => showTab('import')}>01 <span>Import holdings</span></button><button className={tab === 'create' ? 'active' : ''} onClick={() => showTab('create')}>02 <span>Build scenario</span></button><button className={tab === 'history' ? 'active' : ''} onClick={() => showTab('history')}>03 <span>Scenario reports</span></button>{tab === 'report' && <button className="active" onClick={() => {}}>04 <span>Report</span></button>}</nav>
      <div className="ps-content" role="main">
        {error && <div className="ps-error" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
        {tab === 'import' && <div className="ps-page"><div className="ps-section-head"><div><p className="ps-eyebrow">BRING YOUR POSITIONS</p><h2>Import holdings</h2><p>Paste CSV or tabular rows with ticker, shares and optional resource category. Fractional shares are supported. USD stocks and ETFs only for combined valuation.</p></div><span className="ps-step">01 / 03</span></div>
          <div className="ps-import-grid"><div className="ps-panel"><label className="ps-label" htmlFor="ps-import-text">Ticker, shares, optional category</label><textarea id="ps-import-text" value={rawImport} onChange={event => { setRawImport(event.target.value); setPreview(null); }} placeholder={'ticker,shares,category\nAAPL,2.5,0\nSPY,1,11'} /><div className="ps-inline-actions"><label className="ps-file">Choose CSV file<input type="file" accept=".csv,text/csv,text/plain" onChange={async event => { const file = event.target.files?.[0]; if (file) { setRawImport(await file.text()); setPreview(null); } }} /></label><button className="ps-button primary" onClick={previewImport} disabled={busy || !rawImport.trim()}>Review rows <span>→</span></button></div></div><aside className="ps-note"><span className="ps-note-icon">↗</span><h3>Review before adding</h3><p>Ambiguous categories require your choice. Unmatched, unsupported and unavailable securities stay visible so no row is silently skipped.</p><p>Each repeated ticker remains a separate holding. TradeWave's latest closing price gives a current value; no purchase cost basis or brokerage gain is imported.</p></aside></div>
          {preview && <div className="ps-panel ps-review"><div className="ps-review-title"><h3>Import preview</h3><span>{preview.length} rows</span></div><div className="ps-table-wrap"><table><thead><tr><th>Line</th><th>Ticker</th><th>Shares</th><th>Resolution</th><th>Category</th></tr></thead><tbody>{preview.map((row, index) => <tr key={`${row.index}-${index}`}><td>{Number(row.index) + 1}</td><td><strong>{row.symbol}</strong></td><td>{row.shares}</td><td><span className={`ps-pill ${row.status === 'ready' ? 'good' : 'bad'}`}>{row.status.replaceAll('_', ' ')}</span></td><td>{row.matches?.length ? <select aria-label={`Category for ${row.symbol} row ${index + 1}`} value={row.resourceID || ''} onChange={event => updateImportMatch(row.index, event.target.value)}><option value="">Choose category</option>{row.matches.map(match => <option key={match.resourceID} value={match.resourceID}>{match.label || match.name || match.resourceID}</option>)}</select> : row.resourceID || 'No supported match'}</td></tr>)}</tbody></table></div>{importRepeats.length > 0 && <label className="ps-check"><input type="checkbox" checked={duplicateApproved} onChange={event => setDuplicateApproved(event.target.checked)} /> Import repeated tickers as separate holdings: {importRepeats.join(', ')}</label>}<div className="ps-footer-actions"><button className="ps-button primary" onClick={saveImport} disabled={busy || preview.some(row => row.status !== 'ready') || (importRepeats.length > 0 && !duplicateApproved)}>Import {preview.length} reviewed rows</button></div></div>}
        </div>}
        {tab === 'create' && <div className="ps-page"><div className="ps-section-head"><div><p className="ps-eyebrow">BUILD THE STUDY</p><h2>{revision ? 'Revise saved snapshot' : 'New scenario'}</h2><p>{revision ? 'This revision starts from the saved holdings and settings. The original report stays intact.' : 'Current prices anchor each position. Your existing portfolio and saved trade dates stay intact.'}</p></div><span className="ps-step">02 / 03</span></div>
          <div className="ps-build-layout"><div className="ps-build-main"><div className="ps-panel"><div className="ps-card-title"><span className="ps-number">01</span><div><h3>Choose positions</h3><p>Clear all colors to include every row. Edit any missing or zero share quantity before saving.</p></div></div>{!revision && <div className="ps-color-list">{colors.map((label, index) => <label key={index} className={`ps-color-chip ${statuses.includes(String(index)) ? 'selected' : ''}`}><input type="checkbox" checked={statuses.includes(String(index))} onChange={event => setStatuses(previous => event.target.checked ? [...previous, String(index)] : previous.filter(item => item !== String(index)))} /><i style={{ background: index === 0 ? '#9ca7b0' : statusColor[index] }} />{label}</label>)}</div>}<div className="ps-selection-count"><strong>{selected.length}</strong> {selected.length === 1 ? 'position' : 'positions'} in this snapshot</div>{repeats.length > 0 && <div className="ps-duplicate-notice"><strong>Repeated tickers:</strong> {repeats.join(', ')}. Each position is included separately.</div>}<div className="ps-table-wrap ps-holdings-preview"><table><thead><tr><th>Ticker</th><th>Category</th><th>Shares</th><th>Direction</th><th>Status</th></tr></thead><tbody>{selected.map((row, index) => <tr key={`${row.dr_id}-${index}`}><td><strong>{row.symbol}</strong></td><td>{resourceObj?.[Number(row.resourceID)] || "Category unavailable"}</td><td><input aria-label={`${row.symbol} shares row ${index + 1}`} type="number" min="0.000001" step="any" value={shares[row.dr_id] ?? row.shares ?? row.num_shares ?? ''} onChange={event => setShares(previous => ({ ...previous, [row.dr_id]: event.target.value }))} /></td><td><select aria-label={`${row.symbol} direction row ${index + 1}`} value={directions[row.dr_id] || row.direction || 'long'} onChange={event => setDirections(previous => ({ ...previous, [row.dr_id]: event.target.value }))}><option value="long">Long</option><option value="short">Short</option></select></td><td>{colors[Number(row.status || 0)] || 'Unmarked'}</td></tr>)}</tbody></table>{selected.length === 0 && <p className="ps-empty">No holdings in this selection. Import holdings or choose another color.</p>}</div></div>
          <div className="ps-panel"><div className="ps-card-title"><span className="ps-number">02</span><div><h3>Time horizons</h3><p>Entry day is day 1. End dates are inclusive calendar days.</p></div></div><div className="ps-horizons">{HORIZONS.map(item => <label className={horizons.includes(item.key) ? 'selected' : ''} key={item.key}><input type="checkbox" checked={horizons.includes(item.key)} onChange={event => setHorizons(previous => event.target.checked ? [...previous, item.key] : previous.filter(key => key !== item.key))} />{item.label}</label>)}</div>{horizons.includes('custom') && <label className="ps-field">Custom calendar days<input type="number" min="1" max="366" value={customDays} onChange={event => setCustomDays(event.target.value)} /></label>}<label className="ps-field">Historical sample<select value={years} onChange={event => setYears(event.target.value)}>{[10,15,20,30,50].map(count => <option key={count} value={String(count)}>Last {count} consecutive years</option>)}{[0,1,2,3].map(phase => <option key={phase} value={`pe${phase}-10`}>Last 10 PE+{phase} years</option>)}</select><small>Available sample depth depends on your plan and each security's history.</small></label></div></div>
          <aside className="ps-build-side"><div className="ps-panel ps-summary"><p className="ps-eyebrow">SNAPSHOT DETAILS</p><h3>Name this study</h3><label className="ps-field">Report title<input maxLength="120" value={title} onChange={event => setTitle(event.target.value)} placeholder="e.g. Core holdings / autumn" /></label><label className="ps-field">Research notes<textarea maxLength="2000" value={notes} onChange={event => setNotes(event.target.value)} placeholder="Question, thesis, or context…" /></label><div className="ps-summary-line"><span>Selected positions</span><strong>{selected.length}</strong></div><div className="ps-summary-line"><span>Horizons</span><strong>{horizons.length}</strong></div><div className="ps-summary-line"><span>Valuation</span><strong>Current USD prices</strong></div><button className="ps-button primary wide" onClick={createScenario} disabled={busy || !selected.length}>{busy ? 'Building…' : revision ? 'Create revision' : 'Build scenario'} <span>→</span></button><p className="ps-fineprint">Historical outcomes are research, not a forecast. Missing evidence is disclosed in the report.</p></div></aside></div></div>}
        {tab === 'history' && <div className="ps-page"><div className="ps-section-head"><div><p className="ps-eyebrow">SAVED RESEARCH</p><h2>Scenario reports</h2><p>Each report keeps its own positions, quantities, settings and dated result. Revisions add a new snapshot.</p></div><button className="ps-button outline" onClick={loadReports}>Refresh</button></div><div className="ps-history">{reports.map(item => <article className="ps-history-card" key={item.id}><div><span className={`ps-pill ${item.status === 'ready' ? 'good' : item.status === 'failed' ? 'bad' : ''}`}>{item.status}</span><p className="ps-eyebrow">{date(item.created_at)} · {item.holdings_count} holdings</p><h3>{item.title || 'Untitled scenario'}</h3><p>{item.notes || 'No notes added.'}</p><small>{(item.settings?.horizons || []).join(' / ') || 'Horizon details in report'}{item.parent_id ? ' · Revision' : ''}</small></div><div className="ps-history-actions"><button className="ps-button primary" onClick={() => openReport(item.id)}>Open report</button><button className="ps-button subtle-danger" onClick={() => { setDeleteTarget(item); setDeleteAcknowledged(false); }}>Delete Forever</button></div></article>)}{reports.length === 0 && <div className="ps-empty-state"><span>◇</span><h3>No scenario reports yet</h3><p>Choose positions, review horizons, and save your first snapshot.</p><button className="ps-button primary" onClick={() => showTab('create')}>Build a scenario</button></div>}</div></div>}
        {tab === 'report' && report && <div className="ps-report"><div className="ps-report-toolbar"><button className="ps-button outline" onClick={() => showTab('history')}>← All reports</button><div><button className="ps-button outline" onClick={() => { setTitle(report.title || ''); setNotes(report.notes || ''); setEditMeta(true); }}>Edit title & notes</button><button className="ps-button outline" onClick={() => startRevision(report)} disabled={report.status !== 'ready'}>Create revision</button><button className="ps-button outline" onClick={() => downloadCsv(report)} disabled={report.status !== 'ready'}>Download CSV</button><button className="ps-button primary" onClick={printReport} disabled={report.status !== 'ready'}>Print / Save as PDF</button></div></div><div className="ps-print-area"><div className="ps-report-hero"><p className="ps-eyebrow">TRADEWAVE / PRIVATE SCENARIO REPORT</p><div className="ps-report-hero-row"><div><h2>{report.title || 'Portfolio scenario'}</h2><p>{portfolioName} · Saved {date(report.created_at)} · {report.holdings?.length || 0} positions</p></div><div className="ps-hero-value"><span>{report.valuation_label || 'Holdings value'} at snapshot</span><strong>{money(report.base_value ?? selectedReportHorizon?.base_value)}</strong><small>USD closing prices {date(report.base_price_as_of_date)}{report.price_window_gap_days > 0 ? ` · ${report.price_window_gap_days} calendar day(s) before study start` : ''}</small></div></div><p className="ps-report-note">{report.notes}</p></div>
          {report.status === 'running' && <div className="ps-empty-state"><span className="ps-spinner">◌</span><h3>Building the historical study</h3><p>This saved report refreshes automatically while TradeWave processes the windows.</p></div>}
          {report.status === 'failed' && <div className="ps-error">The study could not be completed. {report.error || 'Review available evidence or create a revision.'}</div>}
          {report.status === 'ready' && <><div className="ps-report-horizon-tabs" role="tablist" aria-label="Scenario horizon">{(report.horizons || []).map(item => <button role="tab" aria-selected={item.key === selectedReportHorizon?.key} className={item.key === selectedReportHorizon?.key ? 'active' : ''} key={item.key} onClick={() => setSelectedHorizon(item.key)}>{HORIZONS.find(h => h.key === item.key)?.label || `${item.days} days`}</button>)}</div>
            {selectedReportHorizon && <><div className="ps-metric-grid"><div className="ps-metric"><span>Average scenario value</span><strong>{money(selectedReportHorizon.mean_end_value)}</strong><small>{money(selectedReportHorizon.mean_change)} / {percent(selectedReportHorizon.mean_change_pct)} change</small></div><div className="ps-metric"><span>Median scenario value</span><strong>{money(selectedReportHorizon.median_end_value)}</strong><small>Across completed common years</small></div><div className="ps-metric"><span>Historical outcomes</span><strong>{selectedReportHorizon.positive ?? '-'} <small>positive</small></strong><small>{selectedReportHorizon.flat ?? '-'} flat · {selectedReportHorizon.negative ?? '-'} negative</small></div><div className="ps-metric"><span>Window</span><strong>{selectedReportHorizon.days} <small>days</small></strong><small>{date(selectedReportHorizon.start_date)} - {date(selectedReportHorizon.end_date)}</small></div></div>
              <div className="ps-report-two"><section className="ps-report-card ps-page-break"><div className="ps-card-title"><span className="ps-number">A</span><div><h3>Annual portfolio outcomes</h3><p>Dollar change for each completed historical window.</p></div></div><Bars outcomes={selectedReportHorizon.annual_outcomes} mean={selectedReportHorizon.mean_change} median={selectedReportHorizon.median_change} /><div className="ps-chart-key"><i className="positive" />Positive <i className="negative" />Negative <span>Average {money(selectedReportHorizon.mean_change)} · Median {money(selectedReportHorizon.median_change)}</span></div></section><section className="ps-report-card ps-page-break"><div className="ps-card-title"><span className="ps-number">B</span><div><h3>Evidence & coverage</h3><p>Comparable years across all included holdings.</p></div></div><div className="ps-coverage-number">{selectedReportHorizon.coverage?.count ?? selectedReportHorizon.coverage?.common_years?.length ?? '-'} <span>common years</span></div><p className="ps-muted">{Array.isArray(selectedReportHorizon.coverage?.common_years) ? selectedReportHorizon.coverage.common_years.join(', ') : 'Year details unavailable'}</p><div className="ps-rule" /><p>Current prices anchor this fixed-share scenario. Historical returns come from TradeWave. Every holding must have evidence in a year for that year to enter the common comparison.</p><p className="ps-muted">Sample: {report.settings?.years || 'Unavailable'} · Valuation: USD · Prices dated per holding below.</p><p className="ps-muted">Excluded years without shared evidence: {selectedReportHorizon.coverage?.excluded_years?.join(', ') || 'None'}.</p><p className="ps-muted">ETF positions assume USD-listed shares. Other currency and contract units are unsupported.</p></section></div>
              <section className="ps-report-card ps-page-break"><div className="ps-card-title"><span className="ps-number">C</span><div><h3>Position contributions</h3><p>Holdings remain separate, including repeated tickers. Latest quote and evidence remain visible.</p></div></div><div className="ps-contribution-chart"><Bars outcomes={(selectedReportHorizon.holdings || []).map(item => ({ ...item, change: item.mean_change }))} labelKey="symbol" /></div><div className="ps-table-wrap"><table><thead><tr>{[['symbol','Ticker'],['shares','Shares'],['base_value','Base value'],['weight_pct','Weight'],['mean_change','Avg change'],['mean_return_pct','Avg return'],['mean_end_value','Scenario value'],['positive','Positive'],['ai_status','AI']].map(([key,label]) => <th key={key}><button onClick={() => setSort(sort === key ? `-${key}` : key)}>{label} ↕</button></th>)}</tr></thead><tbody>{[...(selectedReportHorizon.holdings || report.holdings || [])].sort((a,b) => { const key = sort.replace('-', ''); const av = a[key] ?? frozenById[a.dr_id]?.[key], bv = b[key] ?? frozenById[b.dr_id]?.[key]; const comparison = av != null && bv != null && Number.isFinite(Number(av)) && Number.isFinite(Number(bv)) ? Number(av) - Number(bv) : String(av ?? '').localeCompare(String(bv ?? '')); return sort.startsWith('-') ? -comparison : comparison; }).map((item, index) => { const source = frozenById[item.dr_id] || {}; return <tr key={`${item.dr_id}-${index}`}><td><strong>{item.symbol}</strong><small>{item.direction || source.direction || 'long'} · {resourceObj?.[Number(source.resourceID)] || 'Category unavailable'}</small><small>Quote {money(source.price)} · {date(source.price_date)}</small></td><td>{source.shares ?? item.shares}</td><td>{money(item.base_value)}</td><td>{percent(item.weight_pct)}</td><td className={Number(item.mean_change) >= 0 ? 'ps-up' : 'ps-down'}>{money(item.mean_change)}</td><td>{percent(item.mean_return_pct)}</td><td>{money(item.mean_end_value)}</td><td>{item.positive ?? '-'} / {item.count ?? '-'}</td><td>{item.ai_status || 'Unavailable'}</td></tr>; })}</tbody></table></div></section>
              <div className="ps-print-extra">{(report.horizons || []).filter(item => item.key !== selectedReportHorizon.key).map(item => <section className="ps-report-card ps-page-break" key={item.key}><p className="ps-eyebrow">ADDITIONAL HORIZON</p><h3>{HORIZONS.find(h => h.key === item.key)?.label || `${item.days} days`}</h3><p>{date(item.start_date)} - {date(item.end_date)} · {item.days} inclusive calendar days</p><div className="ps-print-metrics"><span>Average value <strong>{money(item.mean_end_value)}</strong></span><span>Median value <strong>{money(item.median_end_value)}</strong></span><span>Average change <strong>{money(item.mean_change)} / {percent(item.mean_change_pct)}</strong></span><span>Positive / flat / negative <strong>{item.positive ?? '-'} / {item.flat ?? '-'} / {item.negative ?? '-'}</strong></span><span>Common years <strong>{item.coverage?.count ?? '-'}</strong></span></div><Bars outcomes={item.annual_outcomes} mean={item.mean_change} median={item.median_change} /><h4>Holding contributions</h4><div className="ps-table-wrap"><table><thead><tr><th>Holding</th><th>Shares</th><th>Base</th><th>Avg change</th><th>Avg return</th><th>Scenario value</th></tr></thead><tbody>{(item.holdings || []).map((holding, index) => <tr key={`${holding.dr_id}-${index}`}><td>{holding.symbol}</td><td>{frozenById[holding.dr_id]?.shares ?? '-'}</td><td>{money(holding.base_value)}</td><td>{money(holding.mean_change)}</td><td>{percent(holding.mean_return_pct)}</td><td>{money(holding.mean_end_value)}</td></tr>)}</tbody></table></div></section>)}</div>
              <section className="ps-report-card ps-page-break"><div className="ps-card-title"><span className="ps-number">D</span><div><h3>Research commentary</h3><p>AI text appears only when the report supplies it.</p></div></div>{report.commentary?.status === 'ready' && report.commentary.text ? <p className="ps-commentary">{report.commentary.text}</p> : <p className="ps-muted">AI commentary {report.commentary?.status || 'unavailable'}.</p>}<div className="ps-report-disclaimer">{Array.isArray(report.assumptions) ? report.assumptions.join(' · ') : 'Fixed shares and USD closing prices.'} Historical results are observations, not promises or investment advice. This report is a private saved snapshot. Downloaded copies remain outside TradeWave after deletion.</div></section></>}
          </>}
        </div></div>}</div>
      {editMeta && <div className="ps-confirm-backdrop"><div className="ps-confirm" role="dialog" aria-modal="true" aria-label="Edit report title and notes"><p className="ps-eyebrow">REPORT DETAILS</p><h3>Edit title & notes</h3><label className="ps-field">Title<input value={title} onChange={event => setTitle(event.target.value)} maxLength="120" /></label><label className="ps-field">Notes<textarea value={notes} onChange={event => setNotes(event.target.value)} maxLength="2000" /></label><div className="ps-inline-actions"><button className="ps-button outline" onClick={() => setEditMeta(false)}>Cancel</button><button className="ps-button primary" disabled={busy || !title.trim()} onClick={updateMetadata}>Save details</button></div></div></div>}
      {deleteTarget && <div className="ps-confirm-backdrop"><div className="ps-confirm" role="alertdialog" aria-modal="true" aria-label="Delete report forever"><p className="ps-eyebrow">PERMANENT ACTION</p><h3>Delete Forever?</h3><p><strong>{deleteTarget.title}</strong> and its hosted report will be removed. This cannot be undone. Previously downloaded files cannot be revoked.</p><label className="ps-check"><input type="checkbox" checked={deleteAcknowledged} onChange={event => setDeleteAcknowledged(event.target.checked)} /> I understand this report will be deleted forever.</label><div className="ps-inline-actions"><button className="ps-button outline" onClick={() => setDeleteTarget(null)}>Keep report</button><button className="ps-button danger" disabled={!deleteAcknowledged || busy} onClick={deleteReport}>Delete Forever</button></div></div></div>}
    </section></div>, document.body);
}

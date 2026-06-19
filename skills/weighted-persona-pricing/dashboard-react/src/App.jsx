import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowUpRight,
  BadgeCheck,
  BarChart3,
  Boxes,
  Brain,
  Database,
  Filter,
  Globe2,
  Layers3,
  LineChart,
  Search,
  ShieldCheck,
  Sparkles,
  UsersRound,
} from 'lucide-react';

const DEMO_DATA = {
  dashboard_data_version: 'demo',
  run: { run_id: 'demo_dashboard', pipeline_status: 'demo', pipeline_version: '0.0.0' },
  method: {
    interview_engine: 'llm_short_all',
    calibration_level: 'synthetic_llm_respondent_uncalibrated',
    order_policy: 'rotate',
    prompt_variant: 'tradeoff',
    prompt_version: 'llm_choice_short_v0_2',
    limitations: ['Synthetic respondent simulation. Not observed sales, survey, or clickstream data.'],
  },
  country_panel: {
    respondent_count: 10000,
    total_weighted_population: 6647003,
    distributions: {
      region: [
        { value: 'Belgrade', weighted_population: 3988202, weighted_share: 0.6, respondent_count: 6000 },
        { value: 'Vojvodina', weighted_population: 2658801, weighted_share: 0.4, respondent_count: 4000 },
      ],
      sex: [
        { value: 'female', weighted_population: 3655852, weighted_share: 0.55, respondent_count: 5500 },
        { value: 'male', weighted_population: 2991151, weighted_share: 0.45, respondent_count: 4500 },
      ],
      income_decile: [
        { value: '8', weighted_population: 3323501, weighted_share: 0.5, respondent_count: 5000 },
        { value: '3', weighted_population: 3323502, weighted_share: 0.5, respondent_count: 5000 },
      ],
    },
  },
  filter_options: { region: ['Belgrade', 'Vojvodina'], sex: ['female', 'male'], income_decile: ['8', '3'] },
  results: {
    record_count: 10000,
    total_weight: 6647003,
    choice_shares: [
      { choice: 'focal_product', share: 0.42, p2_5: 0.39, p97_5: 0.45 },
      { choice: 'competitor', share: 0.37, p2_5: 0.34, p97_5: 0.4 },
      { choice: 'none_or_delay', share: 0.21, p2_5: 0.19, p97_5: 0.24 },
    ],
    top_drivers: [
      { label: 'price_fit', weighted_count: 2800000 },
      { label: 'brand_trust', weighted_count: 2400000 },
      { label: 'feature_fit', weighted_count: 2100000 },
    ],
    top_barriers: [
      { label: 'budget_pressure', weighted_count: 1800000 },
      { label: 'brand_uncertainty', weighted_count: 1400000 },
    ],
  },
  product_scenario: {
    scenario_id: 'smartwatch_demo',
    category: 'smartwatch',
    currency: 'EUR',
    alternatives: [
      { id: 'A', name: 'Huawei Watch Fit 5 Pro', price: 249, normalized_attributes: { price_index: 0.45, brand_strength: 0.68, feature_score: 0.8 } },
      { id: 'B', name: 'Samsung Galaxy Watch 8', price: 329, normalized_attributes: { price_index: 0.66, brand_strength: 0.9, feature_score: 0.88 } },
      { id: 'none', name: 'None / delay purchase', is_outside_option: true },
    ],
  },
  archetypes: [
    {
      archetype_id: 'urban_high_income_high_digital_medium_price',
      label: 'Urban high income, high digital, medium price-sensitive',
      weighted_share: 0.28,
      weighted_population: 1861161,
      respondent_count: 2800,
      profile: { settlement_type: 'urban', income_tier: 'high', digital_intensity: 'high', price_sensitivity: 'medium' },
      choice_shares: { focal_product: 0.32, competitor: 0.52, none_or_delay: 0.16 },
      top_drivers: [{ label: 'brand_trust' }, { label: 'feature_fit' }],
      top_barriers: [{ label: 'higher_price' }],
    },
    {
      archetype_id: 'rural_low_income_low_digital_high_price',
      label: 'Rural low income, low digital, high price-sensitive',
      weighted_share: 0.22,
      weighted_population: 1462341,
      respondent_count: 2200,
      profile: { settlement_type: 'rural', income_tier: 'low', digital_intensity: 'low', price_sensitivity: 'high' },
      choice_shares: { focal_product: 0.49, competitor: 0.19, none_or_delay: 0.32 },
      top_drivers: [{ label: 'price_fit' }],
      top_barriers: [{ label: 'budget_pressure' }],
    },
  ],
  segment_choice_cube: [
    { segment: { region: 'Belgrade' }, segment_level: 'region', weighted_population: 3988202, respondent_count: 6000, low_support: false, choice_shares: { focal_product: 0.39, competitor: 0.43, none_or_delay: 0.18 } },
    { segment: { region: 'Vojvodina' }, segment_level: 'region', weighted_population: 2658801, respondent_count: 4000, low_support: false, choice_shares: { focal_product: 0.47, competitor: 0.28, none_or_delay: 0.25 } },
    { segment: { region: 'Belgrade', sex: 'female' }, segment_level: 'regionxsex', weighted_population: 2193511, respondent_count: 3300, low_support: false, choice_shares: { focal_product: 0.38, competitor: 0.45, none_or_delay: 0.17 } },
  ],
  reason_cube: [
    { segment: { all: 'all' }, choice: 'all', top_drivers: [{ label: 'price_fit' }, { label: 'brand_trust' }], top_barriers: [{ label: 'budget_pressure' }] },
    { segment: { region: 'Belgrade' }, choice: 'competitor', top_drivers: [{ label: 'brand_trust' }, { label: 'ecosystem_fit' }], top_barriers: [{ label: 'higher_price' }] },
  ],
  sample_layers: {
    quantitative_panel: { selected_count: 10000, purpose: 'full weighted quantitative choice estimation and segment filtering' },
    medium_explanation_sample: { selected_count: 1000, purpose: 'medium-detail explanation and reason-code review' },
    deep_case_sample: { selected_count: 100, purpose: 'compact persona case cards and qualitative dashboard examples' },
    deep_case_cards: [
      { persona_id: 'P-0001', archetype_label: 'Urban high income, high digital, medium price-sensitive', population_weight: 681.2, choice: 'competitor', answer_confidence: 'medium', hard: { region: 'Belgrade', sex: 'female', income_decile: '8' }, main_drivers: ['brand_trust', 'feature_fit'], main_barriers: ['higher_price'], switch_conditions: ['discount below 289 EUR'] },
      { persona_id: 'P-0042', archetype_label: 'Rural low income, low digital, high price-sensitive', population_weight: 812.4, choice: 'focal_product', answer_confidence: 'high', hard: { region: 'Vojvodina', sex: 'male', income_decile: '3' }, main_drivers: ['price_fit'], main_barriers: ['brand_uncertainty'], switch_conditions: ['stronger warranty messaging'] },
    ],
  },
  quality: {
    cards: [
      { name: 'IPF / raking', status: 'pass', details: { warnings: 0 } },
      { name: 'Persona coherence', status: 'pass', details: { warnings: 0 } },
      { name: 'LLM choice quality', status: 'review', details: { warnings: 2 } },
    ],
    llm_risk_summary: { warning_count: 2, issue_counts: { low_subgroup_differentiation: 1, possible_position_or_order_bias: 1 }, warnings: [] },
  },
  artifacts: [{ name: 'manifest', path: 'runs/demo/manifest.json' }, { name: 'dashboard_data', path: 'runs/demo/dashboard_data.json' }],
};

const CHOICE_LABELS = {
  focal_product: 'Focal product',
  competitor: 'Competitor',
  none_or_delay: 'None / delay',
};

const CHOICE_TONES = {
  focal_product: 'var(--blue)',
  competitor: 'var(--violet)',
  none_or_delay: 'var(--amber)',
};

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(Number(value));
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function compactNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(Number(value));
}

function titleCase(value) {
  return String(value || '—')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function getDataUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get('data');
}

function matchesSegment(segment = {}, filters = {}) {
  const active = Object.entries(filters).filter(([, value]) => value);
  if (!active.length) return false;
  return active.every(([field, value]) => segment[field] === value) && Object.keys(segment).length === active.length;
}

function chooseSegment(cube = [], filters = {}) {
  const active = Object.entries(filters).filter(([, value]) => value);
  if (!active.length) return null;
  const exact = cube.find((row) => matchesSegment(row.segment, filters));
  if (exact) return { row: exact, exact: true };
  const partials = cube
    .map((row) => {
      const keys = Object.keys(row.segment || {});
      const score = keys.filter((key) => filters[key] && row.segment[key] === filters[key]).length;
      return { row, score };
    })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || (b.row.respondent_count || 0) - (a.row.respondent_count || 0));
  return partials[0] ? { row: partials[0].row, exact: false } : null;
}

function Section({ id, eyebrow, title, subtitle, children }) {
  return (
    <section id={id} className="section">
      <div className="sectionHeader">
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
        {subtitle ? <p className="sectionSubtitle">{subtitle}</p> : null}
      </div>
      {children}
    </section>
  );
}

function MetricCard({ icon: Icon, label, value, helper, tone = 'blue' }) {
  return (
    <article className={`metricCard ${tone}`}>
      <div className="metricIcon" aria-hidden="true"><Icon size={20} /></div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        {helper ? <span>{helper}</span> : null}
      </div>
    </article>
  );
}

function ChoiceBars({ rows = [], compact = false }) {
  const normalized = rows.map((row) => ({
    choice: row.choice,
    share: row.share ?? row.weighted_shares?.[row.choice] ?? row.value ?? 0,
    p2_5: row.p2_5,
    p97_5: row.p97_5,
  }));
  return (
    <div className={compact ? 'choiceBars compact' : 'choiceBars'}>
      {normalized.map((row) => (
        <div className="choiceBar" key={row.choice}>
          <div className="choiceBarTop">
            <span>{CHOICE_LABELS[row.choice] || titleCase(row.choice)}</span>
            <strong>{formatPercent(row.share)}</strong>
          </div>
          <div className="barTrack" aria-label={`${row.choice} ${formatPercent(row.share)}`}>
            <div className="barFill" style={{ width: `${Math.max(0, Math.min(100, row.share * 100))}%`, background: CHOICE_TONES[row.choice] || 'var(--cyan)' }} />
          </div>
          {row.p2_5 !== undefined || row.p97_5 !== undefined ? <small>{formatPercent(row.p2_5)} – {formatPercent(row.p97_5)} interval</small> : null}
        </div>
      ))}
    </div>
  );
}

function DistributionPanel({ distributions = {} }) {
  const fields = Object.entries(distributions).slice(0, 6);
  return (
    <div className="distributionGrid">
      {fields.map(([field, rows]) => (
        <article className="glassCard" key={field}>
          <div className="cardHeader"><h3>{titleCase(field)}</h3><span>{rows.length} groups</span></div>
          <div className="distributionRows">
            {rows.slice(0, 5).map((row) => (
              <div className="distributionRow" key={row.value}>
                <div className="distributionLabel"><strong>{titleCase(row.value)}</strong><span>{formatNumber(row.respondent_count)} respondents</span></div>
                <div className="distributionMetric"><strong>{formatPercent(row.weighted_share)}</strong><span>{compactNumber(row.weighted_population)}</span></div>
                <div className="miniTrack"><div style={{ width: `${Math.max(2, row.weighted_share * 100)}%` }} /></div>
              </div>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}

function ProductScenario({ scenario }) {
  return (
    <div className="productGrid">
      {(scenario?.alternatives || []).map((item) => (
        <article className={item.is_outside_option ? 'productCard outside' : 'productCard'} key={item.id || item.name}>
          <div className="productTop"><span>{item.id || 'Option'}</span>{item.is_outside_option ? <em>Outside option</em> : <em>{scenario.currency || item.currency || ''}</em>}</div>
          <h3>{item.name || 'Unnamed option'}</h3>
          <strong>{item.is_outside_option ? 'Delay / no purchase' : `${formatNumber(item.price)} ${item.currency || scenario.currency || ''}`}</strong>
          <div className="attributeCloud">
            {Object.entries(item.normalized_attributes || {}).slice(0, 5).map(([key, value]) => <span key={key}>{titleCase(key)} · {Number(value).toFixed(2)}</span>)}
          </div>
        </article>
      ))}
    </div>
  );
}

function ArchetypeGrid({ archetypes = [] }) {
  return (
    <div className="archetypeGrid">
      {archetypes.slice(0, 8).map((item) => (
        <article className="archetypeCard" key={item.archetype_id}>
          <div className="archetypeHalo" />
          <div className="cardHeader"><h3>{item.label}</h3><span>{formatPercent(item.weighted_share)}</span></div>
          <p className="muted">Represents {compactNumber(item.weighted_population)} people · {formatNumber(item.respondent_count)} respondents</p>
          <div className="profileTags">
            {Object.entries(item.profile || {}).map(([key, value]) => <span key={key}>{titleCase(key)}: {titleCase(value)}</span>)}
          </div>
          <ChoiceBars compact rows={Object.entries(item.choice_shares || {}).map(([choice, share]) => ({ choice, share }))} />
        </article>
      ))}
    </div>
  );
}

function SegmentExplorer({ data }) {
  const options = data.filter_options || {};
  const [filters, setFilters] = useState({});
  const segment = useMemo(() => chooseSegment(data.segment_choice_cube || [], filters), [data.segment_choice_cube, filters]);
  const activeChoices = segment?.row?.choice_shares
    ? Object.entries(segment.row.choice_shares).map(([choice, share]) => ({ choice, share }))
    : data.results?.choice_shares || [];

  function setFilter(field, value) {
    setFilters((prev) => ({ ...prev, [field]: value || '' }));
  }

  return (
    <div className="segmentPanel">
      <div className="filterRail">
        {Object.entries(options).slice(0, 8).map(([field, values]) => (
          <label key={field}>
            <span>{titleCase(field)}</span>
            <select value={filters[field] || ''} onChange={(event) => setFilter(field, event.target.value)}>
              <option value="">All</option>
              {values.map((value) => <option value={value} key={value}>{titleCase(value)}</option>)}
            </select>
          </label>
        ))}
        <button className="ghostButton" type="button" onClick={() => setFilters({})}><Filter size={16} /> Reset filters</button>
      </div>
      <article className="segmentResult">
        <div className="cardHeader">
          <div>
            <p className="eyebrow">Selected segment</p>
            <h3>{segment ? Object.entries(segment.row.segment).map(([k, v]) => `${titleCase(k)}: ${titleCase(v)}`).join(' · ') : 'All respondents'}</h3>
          </div>
          {segment ? <span className={segment.exact ? 'statusPill pass' : 'statusPill review'}>{segment.exact ? 'Exact cube' : 'Nearest cube'}</span> : <span className="statusPill pass">Overall</span>}
        </div>
        <div className="segmentMetrics">
          <MetricCard icon={UsersRound} label="Respondents" value={formatNumber(segment?.row?.respondent_count || data.country_panel?.respondent_count)} helper={segment?.row?.low_support ? 'Low support warning' : 'Synthetic support'} />
          <MetricCard icon={Globe2} label="Weighted population" value={compactNumber(segment?.row?.weighted_population || data.country_panel?.total_weighted_population)} helper="Represented people" tone="violet" />
        </div>
        <ChoiceBars rows={activeChoices} />
      </article>
    </div>
  );
}

function ReasonsPanel({ data }) {
  const overall = data.reason_cube?.find((item) => item.segment?.all === 'all') || {};
  return (
    <div className="reasonsGrid">
      <ReasonList title="Overall drivers" items={data.results?.top_drivers || overall.top_drivers || []} icon={Sparkles} />
      <ReasonList title="Overall barriers" items={data.results?.top_barriers || overall.top_barriers || []} icon={AlertTriangle} />
      <article className="glassCard wideReason">
        <div className="cardHeader"><h3>Segment reason snapshots</h3><span>{data.reason_cube?.length || 0} cubes</span></div>
        <div className="reasonSnapshots">
          {(data.reason_cube || []).filter((item) => item.choice !== 'all').slice(0, 6).map((item, index) => (
            <div className="reasonSnapshot" key={`${item.choice}-${index}`}>
              <strong>{CHOICE_LABELS[item.choice] || titleCase(item.choice)}</strong>
              <span>{Object.entries(item.segment || {}).map(([k, v]) => `${titleCase(k)} ${titleCase(v)}`).join(' · ')}</span>
              <p>{(item.top_drivers || []).slice(0, 2).map((driver) => driver.label).join(' / ') || 'No drivers recorded'}</p>
            </div>
          ))}
        </div>
      </article>
    </div>
  );
}

function ReasonList({ title, items = [], icon: Icon }) {
  return (
    <article className="glassCard">
      <div className="cardHeader"><h3>{title}</h3><Icon size={18} /></div>
      <div className="reasonList">
        {items.slice(0, 8).map((item, index) => (
          <div className="reasonItem" key={`${item.label}-${index}`}>
            <span>{index + 1}</span>
            <strong>{titleCase(item.label)}</strong>
            <em>{compactNumber(item.weighted_count)}</em>
          </div>
        ))}
      </div>
    </article>
  );
}

function QualityAudit({ quality = {}, method = {} }) {
  const cards = quality.cards || [];
  const risks = quality.llm_risk_summary || {};
  return (
    <div className="auditGrid">
      <article className="glassCard methodCard">
        <div className="cardHeader"><h3>Method boundary</h3><ShieldCheck size={18} /></div>
        <dl>
          <dt>Engine</dt><dd>{method.interview_engine || '—'}</dd>
          <dt>Calibration</dt><dd>{method.calibration_level || '—'}</dd>
          <dt>Prompt</dt><dd>{method.prompt_version || '—'} · {method.prompt_variant || '—'}</dd>
          <dt>Order policy</dt><dd>{method.order_policy || '—'}</dd>
        </dl>
        <p className="warningCopy">Synthetic respondent simulation. Not observed consumer behavior. Decision-grade claims require calibration.</p>
      </article>
      <article className="glassCard auditCards">
        <div className="cardHeader"><h3>Audit cards</h3><BadgeCheck size={18} /></div>
        <div className="auditList">
          {cards.map((card) => <div className="auditItem" key={card.name}><span className={`statusDot ${card.status}`} /><strong>{card.name}</strong><em>{card.status}</em></div>)}
        </div>
      </article>
      <article className="glassCard riskCard">
        <div className="cardHeader"><h3>LLM risk signals</h3><AlertTriangle size={18} /></div>
        <strong className="riskNumber">{risks.warning_count || 0}</strong>
        <p>Warnings are diagnostics, not automatic invalidation.</p>
        <div className="profileTags">
          {Object.entries(risks.issue_counts || {}).map(([key, value]) => <span key={key}>{titleCase(key)}: {value}</span>)}
        </div>
      </article>
    </div>
  );
}

function CaseCards({ cards = [] }) {
  return (
    <div className="caseGrid">
      {cards.slice(0, 12).map((card) => (
        <article className="caseCard" key={card.persona_id}>
          <div className="caseTop"><span>{card.persona_id}</span><em>{card.answer_confidence || 'confidence —'}</em></div>
          <h3>{card.archetype_label}</h3>
          <p>{Object.entries(card.hard || {}).map(([key, value]) => `${titleCase(key)}: ${titleCase(value)}`).join(' · ')}</p>
          <div className="caseChoice" style={{ color: CHOICE_TONES[card.choice] || 'var(--text)' }}>{CHOICE_LABELS[card.choice] || titleCase(card.choice)}</div>
          <div className="caseReasons"><strong>Drivers</strong><span>{(card.main_drivers || []).join(' / ') || '—'}</span></div>
          <div className="caseReasons"><strong>Barriers</strong><span>{(card.main_barriers || []).join(' / ') || '—'}</span></div>
        </article>
      ))}
    </div>
  );
}

function AppHeader({ data, sourceLabel }) {
  const panel = data.country_panel || {};
  return (
    <header className="hero">
      <div className="aurora" />
      <nav className="topNav" aria-label="Dashboard sections">
        <span className="brand"><Sparkles size={18} /> Silicon Sampling</span>
        <div>
          <a href="#segments">Segments</a>
          <a href="#audit">Audit</a>
          <a href="#cases">Cases</a>
        </div>
      </nav>
      <div className="heroGrid">
        <div>
          <p className="eyebrow">Census-weighted synthetic respondent panel</p>
          <h1>Market choice intelligence without losing the research trail.</h1>
          <p className="heroCopy">A premium dashboard for country-level synthetic panels, all-persona choice simulation, segment exploration, drivers, barriers, and audit diagnostics.</p>
          <div className="heroBadges">
            <span><Database size={15} /> {sourceLabel}</span>
            <span><Layers3 size={15} /> {data.method?.interview_engine || 'engine —'}</span>
            <span><ShieldCheck size={15} /> Not observed market data</span>
          </div>
        </div>
        <div className="heroMetrics">
          <MetricCard icon={UsersRound} label="Synthetic respondents" value={formatNumber(panel.respondent_count)} helper="Active run panel" />
          <MetricCard icon={Globe2} label="Weighted population" value={compactNumber(panel.total_weighted_population)} helper="People represented" tone="violet" />
          <MetricCard icon={Brain} label="Medium / deep layers" value={`${formatNumber(data.sample_layers?.medium_explanation_sample?.selected_count)} / ${formatNumber(data.sample_layers?.deep_case_sample?.selected_count)}`} helper="Explanation samples" tone="amber" />
        </div>
      </div>
    </header>
  );
}

export function App() {
  const [data, setData] = useState(DEMO_DATA);
  const [loading, setLoading] = useState(Boolean(getDataUrl()));
  const [error, setError] = useState(null);
  const sourceLabel = getDataUrl() || 'embedded demo data';

  useEffect(() => {
    const dataUrl = getDataUrl();
    if (!dataUrl) return;
    const controller = new AbortController();
    async function load() {
      try {
        setLoading(true);
        const response = await fetch(new URL(dataUrl, window.location.href), { signal: controller.signal });
        if (!response.ok) throw new Error(`Unable to load dashboard data: ${response.status}`);
        const payload = await response.json();
        setData(payload);
      } catch (err) {
        if (err.name !== 'AbortError') setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, []);

  const topStats = data.results?.choice_shares || [];

  return (
    <main>
      <AppHeader data={data} sourceLabel={sourceLabel} />
      {error ? <div className="loadError"><AlertTriangle size={18} /> {error}. Showing demo data.</div> : null}
      {loading ? <div className="loadingState">Loading dashboard data…</div> : null}

      <section className="quickGrid">
        <MetricCard icon={LineChart} label="Records" value={formatNumber(data.results?.record_count)} helper="Choice rows" />
        <MetricCard icon={BarChart3} label="Top choice" value={titleCase(topStats[0]?.choice)} helper={formatPercent(topStats[0]?.share)} tone="violet" />
        <MetricCard icon={Boxes} label="Archetypes" value={formatNumber(data.archetypes?.length)} helper="Representative profiles" tone="amber" />
        <MetricCard icon={ShieldCheck} label="Quality warnings" value={formatNumber(data.quality?.llm_risk_summary?.warning_count || 0)} helper="Diagnostic only" tone="cyan" />
      </section>

      <Section id="results" eyebrow="01 · Market result" title="Weighted choice shares" subtitle="The quantitative answer from the active country run. Intervals are shown when bootstrap artifacts are available.">
        <div className="twoColumn">
          <article className="featureCard"><ChoiceBars rows={data.results?.choice_shares || []} /></article>
          <ProductScenario scenario={data.product_scenario || {}} />
        </div>
      </Section>

      <Section id="population" eyebrow="02 · Population structure" title="Country panel distribution" subtitle="Weighted distributions from the active synthetic panel. Raw respondent counts are shown as support, not as population shares.">
        <DistributionPanel distributions={data.country_panel?.distributions || {}} />
      </Section>

      <Section id="archetypes" eyebrow="03 · Representative profiles" title="Synthetic archetypes" subtitle="Compact explanation groups derived from the active run. They are descriptive profiles, not official population classes.">
        <ArchetypeGrid archetypes={data.archetypes || []} />
      </Section>

      <Section id="segments" eyebrow="04 · Segment explorer" title="Filter a population, see the choice mix" subtitle="Use precomputed segment cubes to inspect weighted choice shares for selected groups.">
        <SegmentExplorer data={data} />
      </Section>

      <Section id="reasons" eyebrow="05 · Decision reasons" title="Drivers and barriers" subtitle="Aggregated reason codes from respondent-level choice rows. Segment snapshots show how motivation changes by group.">
        <ReasonsPanel data={data} />
      </Section>

      <Section id="audit" eyebrow="06 · Method integrity" title="Quality and audit trail" subtitle="The dashboard always shows the conditions under which the result was produced.">
        <QualityAudit quality={data.quality || {}} method={data.method || {}} />
      </Section>

      <Section id="cases" eyebrow="07 · Qualitative layer" title="Deep case cards" subtitle="A compact 100-person layer for interpretability. These cards explain; they do not estimate market share.">
        <CaseCards cards={data.sample_layers?.deep_case_cards || []} />
      </Section>

      <footer className="footer">
        <span>Generated from dashboard_data.json</span>
        <span>Artifacts retained: {formatNumber(data.artifacts?.length || 0)}</span>
        <a href="#results">Back to top <ArrowUpRight size={14} /></a>
      </footer>
    </main>
  );
}

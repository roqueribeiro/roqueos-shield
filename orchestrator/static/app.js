/* Dashboard antigo do RoqueShield em /ui (servido só quando não existe o build da
 * tela nova em orchestrator/web_dist).
 *
 * Dois componentes Alpine (build CSP, sem eval, registrados por Alpine.data):
 *   dashboard  em index.html  (4 abas, polling 3s, gráficos)
 *   cockpit    em cockpit.html (1 scan, SSE de fase e logs)
 *
 * Autenticação: só o cookie HttpOnly `rs_session`, o mesmo da tela nova. O JavaScript
 * não lê, não guarda e não manda token nenhum: o login é POST /auth/session (ou
 * POST /setup no primeiro uso), o navegador guarda o cookie e o devolve sozinho no
 * mesmo endereço, inclusive no EventSource do SSE. Escrita leva o cabeçalho
 * X-RoqueShield, que o shield exige quando a credencial é o cookie (CSRF).
 *
 * O build CSP do Alpine só entende expressão simples no HTML (sem template string,
 * arrow function, `?.` ou `??`): o que for mais que isso vira método aqui.
 */

const POLL_MS = 3000;
const CABECALHO_CSRF = 'X-RoqueShield';

// -------------------- HTTP (cookie de sessão, nada de token) --------------------

async function api(path, { method = 'GET', body } = {}) {
  const headers = { Accept: 'application/json' };
  if (method !== 'GET' && method !== 'HEAD') headers[CABECALHO_CSRF] = '1';
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const r = await fetch(path, {
    method,
    headers,
    credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  const tipo = r.headers.get('content-type') || '';
  if (tipo.includes('application/json')) {
    try { data = await r.json(); } catch { data = null; }
  }
  return { ok: r.ok, status: r.status, data };
}

function erroDe(resp) {
  const d = resp.data && resp.data.detail;
  if (typeof d === 'string') return d;
  if (resp.status === 429) return 'muitas tentativas; espere um pouco';
  return 'falhou (HTTP ' + resp.status + ')';
}

// -------------------- helpers globais --------------------

function fmtTime(iso) {
  if (!iso) return '-';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const now = new Date();
    if (d.toDateString() === now.toDateString()) {
      return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
}

function nowFmt() {
  return new Date().toLocaleTimeString('pt-BR');
}

function stateColor(state) {
  return {
    'pending':  'bg-muted/20 text-muted',
    'running':  'bg-accent/20 text-accent',
    'done':     'bg-ok/20 text-ok',
    'failed':   'bg-down/20 text-down',
    'canceled': 'bg-warn/20 text-warn',
  }[state] || 'bg-muted/20 text-muted';
}

function sevColor(sev) {
  return {
    'critical': 'bg-down/30 text-down',
    'high':     'bg-warn/30 text-warn',
    'medium':   'bg-accent/30 text-accent',
    'low':      'bg-ok/30 text-ok',
    'info':     'bg-muted/30 text-muted',
  }[sev] || 'bg-muted/20 text-muted';
}

function logLevelColor(lvl) {
  return {
    'debug':   'text-muted',
    'info':    'text-accent',
    'warning': 'text-warn',
    'error':   'text-down',
    'critical':'text-down',
  }[lvl] || 'text-slate-400';
}

function logRest(l) {
  // Mostra os campos extras (sem level/event/timestamp/_received_at/_key)
  const { level, event, timestamp, _received_at, _key, ...rest } = l;
  return Object.keys(rest).length ? JSON.stringify(rest) : '';
}

function logTime(l, vazio) {
  return (l && l.timestamp) ? String(l.timestamp).slice(11, 19) : vazio;
}

let _seqLog = 0;
function logKey(l) {
  // chave pra Alpine não duplicar em re-render
  _seqLog += 1;
  return (l.timestamp || '') + '-' + (l.event || '') + '-' + _seqLog;
}

function abrirSSE(alvo, url, aoFase) {
  // Mesmo endereço: o EventSource leva o cookie de sessão sozinho, sem ?token=.
  const src = new EventSource(url);
  src.addEventListener('open', () => { alvo.sseConnected = true; });
  src.addEventListener('error', () => { alvo.sseConnected = false; });
  src.addEventListener('log', (e) => {
    try {
      const data = JSON.parse(e.data);
      data._key = logKey(data);
      alvo.logs.push(data);
      if (alvo.logs.length > 500) alvo.logs = alvo.logs.slice(-500);
    } catch (err) { console.warn('log SSE ilegível', err); }
  });
  if (aoFase) {
    src.addEventListener('phase', (e) => {
      try { aoFase(JSON.parse(e.data)); } catch (err) { console.warn('fase SSE ilegível', err); }
    });
  }
  return src;
}

// -------------------- Dashboard component --------------------

function dashboard() {
  return {
    screen: 'loading',
    needsSetup: false,
    busy: false,
    loginError: '',
    form: { email: '', name: '', password: '', setup_code: '' },
    account: { email: '' },
    activeTab: 'dashboard',
    tabs: [
      { id: 'dashboard', icon: '◉', label: 'Dashboard', subtitle: 'Visão geral da stack e atividade', badge: null },
      { id: 'scans',     icon: '⚡', label: 'Scans',     subtitle: 'Pentests executados',                badge: null },
      { id: 'ai',        icon: '✦', label: 'AI Calls',  subtitle: 'Chamadas LLM (litellm)',             badge: null },
      { id: 'logs',      icon: '⌗', label: 'Logs',       subtitle: 'Stream de eventos do orchestrator',  badge: null },
    ],
    health: { components: [], overall: 'ok' },
    overallStatus: 'ok',
    version: '',
    scans: [],
    aiRuns: [],
    aiStats: {},
    logs: [],
    sseConnected: false,
    sseSource: null,
    logFilter: '',
    pollTimer: null,
    chartModels: null,
    chartSeverity: null,

    // Alpine chama init() sozinho; não repetir em x-init (polling dobrado).
    async init() {
      await this.checkSession();
    },

    async checkSession() {
      const eu = await api('/auth/session');
      if (eu.ok && eu.data) {
        this.account = eu.data;
        this.startApp();
        return;
      }
      const setup = await api('/setup');
      this.needsSetup = !!(setup.ok && setup.data && setup.data.needs_setup);
      if (setup.ok && setup.data) this.version = setup.data.version || '';
      this.screen = 'login';
    },

    loginTitle() {
      return this.needsSetup ? 'Primeiro uso: crie a conta de administrador' : 'Entrar';
    },

    submitLabel() {
      if (this.busy) return '...';
      return this.needsSetup ? 'Criar conta e entrar' : 'Entrar';
    },

    async submitLogin() {
      this.busy = true;
      this.loginError = '';
      try {
        const resp = this.needsSetup
          ? await api('/setup', { method: 'POST', body: {
              email: this.form.email,
              name: this.form.name || null,
              password: this.form.password,
              setup_code: this.form.setup_code || null,
            } })
          : await api('/auth/session', { method: 'POST', body: {
              email: this.form.email, password: this.form.password,
            } });
        if (!resp.ok) { this.loginError = erroDe(resp); return; }
        this.form.password = '';
        this.form.setup_code = '';
        this.account = resp.data || { email: this.form.email };
        this.startApp();
      } finally {
        this.busy = false;
      }
    },

    async logout() {
      await api('/auth/session', { method: 'DELETE' });
      this.stopApp();
      this.account = { email: '' };
      this.screen = 'login';
    },

    startApp() {
      this.screen = 'app';
      this.refresh();
      if (!this.pollTimer) this.pollTimer = setInterval(() => this.refresh(), POLL_MS);
      this.connectSSE();
    },

    stopApp() {
      if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; }
      this.disconnectSSE();
    },

    sessionLost() {
      // 401 no meio do uso: sessão expirou ou foi derrubada (logout em outra aba).
      this.stopApp();
      this.screen = 'login';
    },

    selectTab(id) { this.activeTab = id; },
    currentTab() { return this.tabs.find(t => t.id === this.activeTab) || this.tabs[0]; },
    footerText() { return 'v' + (this.version || '...') + ' · ' + nowFmt(); },
    clearLogs() { this.logs = []; },
    cockpitUrl(s) { return 'cockpit.html?scan_id=' + encodeURIComponent(s.id); },

    healthComponents() { return (this.health && this.health.components) || []; },
    componentDetail(c) {
      const d = c.detail || {};
      return d.error || d.version || (d.models || []).join(', ') || (d.keys_configured || []).join(', ') || '';
    },
    aiTotal() { return this.aiStats.total ?? 0; },
    aiSuccessRate() { return ((this.aiStats.success_rate ?? 1) * 100).toFixed(0) + '%'; },
    aiLatency(campo) { return this.aiStats[campo] ?? 0; },
    aiFallbackRate() { return ((this.aiStats.fallback_rate ?? 0) * 100).toFixed(1); },

    async refresh() {
      if (this.screen !== 'app') return;
      await Promise.all([
        this.loadHealth(),
        this.loadScans(),
        this.loadAIRuns(),
        this.loadAIStats(),
        this.loadVersion(),
      ]);
      this.renderCharts();
    },

    async fetchJson(path) {
      try {
        const r = await api(path);
        if (r.status === 401) { this.sessionLost(); return null; }
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.data;
      } catch (e) {
        console.warn('fetch failed', path, e.message);
        return null;
      }
    },

    async loadHealth() {
      const data = await this.fetchJson('/health/full');
      if (data) {
        this.health = data;
        this.overallStatus = data.overall;
      } else {
        this.overallStatus = 'down';
      }
    },

    async loadVersion() {
      const data = await this.fetchJson('/health');
      if (data) this.version = data.version;
    },

    async loadScans() {
      const data = await this.fetchJson('/ui/api/scans?limit=50');
      if (data) this.scans = data;
    },

    async loadAIRuns() {
      const data = await this.fetchJson('/ui/api/ai-runs?limit=100');
      if (data) this.aiRuns = data;
    },

    async loadAIStats() {
      const data = await this.fetchJson('/ui/api/ai-runs/stats');
      if (data) this.aiStats = data;
    },

    renderCharts() {
      if (typeof Chart === 'undefined') return;
      // Models doughnut
      const ctxM = document.getElementById('chartModels');
      if (ctxM && this.aiStats.by_model) {
        const labels = this.aiStats.by_model.map(m => m.model.split('/').pop());
        const counts = this.aiStats.by_model.map(m => m.count);
        if (this.chartModels) this.chartModels.destroy();
        this.chartModels = new Chart(ctxM, {
          type: 'doughnut',
          data: { labels, datasets: [{
            data: counts,
            backgroundColor: ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#64748b'],
            borderColor: '#111a2c', borderWidth: 2,
          }] },
          options: { plugins: { legend: { position: 'right', labels: { color: '#cbd5e1', font: { size: 11 } } } } }
        });
      }

      // Severity stacked bar (10 últimos scans)
      const ctxS = document.getElementById('chartSeverity');
      if (ctxS && this.scans.length) {
        const last = this.scans.slice(0, 10).reverse();
        const labels = last.map(s => s.id.slice(0, 6));
        const sevs = ['critical', 'high', 'medium', 'low', 'info'];
        const colors = { critical: '#ef4444', high: '#f59e0b', medium: '#3b82f6', low: '#10b981', info: '#64748b' };
        const datasets = sevs.map(sev => ({
          label: sev,
          data: last.map(s => s.severity_counts[sev] || 0),
          backgroundColor: colors[sev],
        }));
        if (this.chartSeverity) this.chartSeverity.destroy();
        this.chartSeverity = new Chart(ctxS, {
          type: 'bar',
          data: { labels, datasets },
          options: {
            responsive: true,
            scales: {
              x: { stacked: true, ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: '#1e293b' } },
              y: { stacked: true, ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: '#1e293b' } }
            },
            plugins: { legend: { labels: { color: '#cbd5e1', font: { size: 11 } } } }
          }
        });
      }
    },

    connectSSE() {
      if (this.sseSource) return;
      this.sseSource = abrirSSE(this, '/ui/api/events');
    },

    disconnectSSE() {
      if (this.sseSource) { this.sseSource.close(); this.sseSource = null; this.sseConnected = false; }
    },

    logsFiltered() {
      if (!this.logFilter) return this.logs.slice(-200);
      const f = this.logFilter.toLowerCase();
      return this.logs.filter(l =>
        (l.event || '').toLowerCase().includes(f) ||
        (l.level || '').toLowerCase().includes(f) ||
        JSON.stringify(l).toLowerCase().includes(f)
      ).slice(-200);
    },

    nowFmt, fmtTime, stateColor, sevColor, logLevelColor, logRest, logTime,
  };
}

// -------------------- Cockpit component --------------------

function cockpit() {
  return {
    scanId: '',
    scan: null,
    findings: [],
    logs: [],
    needsLogin: false,
    missingScan: false,
    sseConnected: false,
    sseSource: null,
    pollTimer: null,
    phaseProgress: null,
    phases: [
      { key: 'queued',          label: 'queued' },
      { key: 'nmap_running',    label: 'nmap' },
      { key: 'zap_running',     label: 'zap' },
      { key: 'dedup',           label: 'dedup' },
      { key: 'ai_triage',       label: 'triage' },
      { key: 'persisting',      label: 'persist' },
      { key: 'reporting',       label: 'report' },
      { key: 'done',            label: 'done' },
    ],

    init() {
      const params = new URLSearchParams(location.search);
      this.scanId = params.get('scan_id') || '';
      if (!this.scanId) { this.missingScan = true; return; }
      this.refresh();
      this.pollTimer = setInterval(() => this.refresh(), POLL_MS);
      this.connectSSE();
    },

    async fetchJson(path) {
      try {
        const r = await api(path);
        if (r.status === 401) { this.stop(); this.needsLogin = true; return null; }
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.data;
      } catch (e) {
        console.warn('fetch failed', path, e.message);
        return null;
      }
    },

    stop() {
      if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; }
      if (this.sseSource) { this.sseSource.close(); this.sseSource = null; this.sseConnected = false; }
    },

    async refresh() {
      const id = encodeURIComponent(this.scanId);
      const [scan, findings] = await Promise.all([
        this.fetchJson('/ui/api/scans/' + id),
        this.fetchJson('/ui/api/findings?scan_id=' + id + '&limit=200'),
      ]);
      if (scan) {
        this.scan = scan;
        this.phaseProgress = scan.phase_progress;
      }
      if (findings) {
        // ordena por severity rank (critical primeiro)
        const rank = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
        this.findings = findings.sort((a, b) => (rank[a.severity] ?? 9) - (rank[b.severity] ?? 9));
      }
    },

    connectSSE() {
      const url = '/ui/api/events?scan_id=' + encodeURIComponent(this.scanId);
      this.sseSource = abrirSSE(this, url, (data) => {
        if (data.scan_id === this.scanId) {
          // forçar refresh de scan pra ver o phase update
          this.phaseProgress = data.progress;
          this.refresh();
        }
      });
    },

    scanState() { return this.scan ? this.scan.state : ''; },
    targetLabel() { return (this.scan && this.scan.target && this.scan.target.value) || 'carregando...'; },
    scanAiRuns() { return (this.scan && this.scan.ai_runs) || []; },
    hasReport() { return !!(this.scan && this.scan.report_path); },
    recentLogs() { return this.logs.slice(-200); },
    aiRunMeta(r) { return r.prompt_tokens + 'p/' + r.completion_tokens + 'c · ' + r.finding_count + ' findings'; },
    findingsCountText() {
      const sc = (this.scan && this.scan.severity_counts) || {};
      const total = Object.values(sc).reduce((a, b) => a + b, 0);
      return this.findings.length + ' de ' + total;
    },
    // O cookie vai junto no link do mesmo endereço: nada de ?token= na URL.
    bundleUrl() { return '/reports/' + encodeURIComponent(this.scanId) + '/ai-bundle'; },
    reportUrl() { return '/reports/' + encodeURIComponent(this.scanId); },

    elapsed() {
      if (!this.scan || !this.scan.started_at) return '';
      const start = new Date(this.scan.started_at).getTime();
      const end = this.scan.finished_at ? new Date(this.scan.finished_at).getTime() : Date.now();
      const sec = Math.floor((end - start) / 1000);
      const m = Math.floor(sec / 60), s = sec % 60;
      return m > 0 ? m + 'm ' + s + 's' : s + 's';
    },

    phaseStatus(key) {
      const cur = this.scan ? this.scan.current_phase : null;
      if (!cur) return 'pending';
      // ordem das fases pra inferir "passou já"
      const order = this.phases.map(p => p.key);
      const idxCur = order.indexOf(cur === 'failed' ? 'done' : cur);
      const idxKey = order.indexOf(key);
      // mapeia zap_spider/passive/active -> zap_running pra UI
      const norm = (cur === 'zap_spider' || cur === 'zap_passive' || cur === 'zap_active') ? 'zap_running' : cur;
      if (norm === key) return this.scan.state === 'failed' ? 'failed' : 'running';
      if (idxKey < idxCur) return 'done';
      return 'pending';
    },

    phaseStyle(key) {
      const st = this.phaseStatus(key);
      return {
        'done':    'bg-ok/20 text-ok ring-1 ring-ok/40',
        'running': 'bg-accent/30 text-accent ring-2 ring-accent animate-pulse',
        'failed':  'bg-down/30 text-down ring-2 ring-down',
        'pending': 'bg-panel border border-border text-muted',
      }[st];
    },

    phaseIcon(key) {
      const st = this.phaseStatus(key);
      return { done: '✓', running: '⚡', failed: '✗', pending: '○' }[st];
    },

    sevColor, stateColor, logLevelColor, logRest, logTime, fmtTime,
  };
}

// O build CSP do Alpine não avalia `dashboard()` no x-data: o componente é registrado
// por nome e o HTML diz só `x-data="dashboard"`. Este arquivo carrega antes do Alpine.
document.addEventListener('alpine:init', () => {
  window.Alpine.data('dashboard', dashboard);
  window.Alpine.data('cockpit', cockpit);
});

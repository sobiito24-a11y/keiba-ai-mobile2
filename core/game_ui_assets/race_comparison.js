/* Display-only table controls. Prediction records and saved archives are read-only. */
(() => {
  'use strict';

  const numericType = type => type === 'number' || type === 'rank';
  const missing = (value, type) => numericType(type)
    ? typeof value !== 'number' || !Number.isFinite(value)
    : type === 'boolean' ? typeof value !== 'boolean'
      : typeof value !== 'string' || !value.trim();
  const folded = value => String(value ?? '').normalize('NFKC').toLocaleLowerCase('ja');
  const collator = new Intl.Collator('ja', {numeric: true, sensitivity: 'base'});

  function compareValues(a, b, type, direction = 'asc') {
    const am = missing(a, type), bm = missing(b, type);
    // Unknown values always remain last, including descending order.
    if (am !== bm) return am ? 1 : -1;
    if (am) return 0;
    const order = numericType(type) || type === 'boolean'
      ? (a === b ? 0 : a < b ? -1 : 1) : collator.compare(a, b);
    return (direction === 'desc' ? -1 : 1) * order;
  }

  function cleanFilter(raw, spec) {
    if (!raw || typeof raw !== 'object' || !spec) return null;
    const result = {presence: ['known', 'missing'].includes(raw.presence) ? raw.presence : 'all'};
    if (result.presence === 'missing') return {presence: 'missing'};
    if (numericType(spec.type)) {
      for (const field of ['min', 'max']) {
        if (raw[field] !== '' && raw[field] !== null && raw[field] !== undefined) {
          const number = Number(raw[field]);
          if (!Number.isFinite(number)) throw new RangeError('範囲には有効な数値を入力してください。');
          result[field] = number;
        }
      }
      if (result.min !== undefined && result.max !== undefined && result.min > result.max)
        throw new RangeError('下限は上限以下にしてください。');
    }
    if (spec.type === 'text' || spec.text_key) {
      if (typeof raw.text === 'string' && raw.text.trim()) result.text = raw.text.trim();
    }
    if (spec.type === 'grade' && ['A', 'B', 'C', 'D'].includes(raw.choice)) result.choice = raw.choice;
    if (spec.type === 'boolean' && ['selected', 'unselected'].includes(raw.choice)) result.choice = raw.choice;
    return Object.keys(result).length > 1 || result.presence !== 'all' ? result : null;
  }

  function matchesFilter(value, filter, spec, textValue) {
    if (!filter) return true;
    const absent = missing(value, spec.type);
    if (filter.presence === 'missing') return absent;
    if (filter.presence === 'known' && absent) return false;
    if (filter.min !== undefined && (absent || value < filter.min)) return false;
    if (filter.max !== undefined && (absent || value > filter.max)) return false;
    if (filter.choice !== undefined) {
      if (spec.type === 'boolean') {
        if (absent || value !== (filter.choice === 'selected')) return false;
      } else if (absent || value !== filter.choice) return false;
    }
    if (filter.text && !folded(spec.text_key ? textValue : value).includes(folded(filter.text))) return false;
    return true;
  }

  // The pure comparison/filter rules can also be checked without a browser.
  if (typeof module !== 'undefined' && module.exports)
    module.exports = {compareValues, cleanFilter, matchesFilter, missing};
  if (typeof document === 'undefined') return;
  const data = JSON.parse(document.getElementById('race-data').textContent);
  if (data.experience !== 'race-comparison' || !Array.isArray(data.columns)) return;

  if (window.keibaComparison && window.keibaComparison.dispose) window.keibaComparison.dispose();
  const byId = id => document.getElementById(id);
  const specs = new Map(data.columns.map(spec => [spec.key, spec]));
  const horses = new Map(data.horses.map(horse => [String(horse.no), horse]));
  const body = document.querySelector('.explorer-table tbody');
  const tableScroll = document.querySelector('.explorer-table-scroll');
  const stateKey = 'keiba-comparison-workspace:' + data.race_key;
  const manualKey = 'keiba-manual-comparison:' + data.race_key;
  let saved = {};
  let disposed = false;
  try {
    const stored = JSON.parse(sessionStorage.getItem(stateKey) || '{}');
    if (stored && typeof stored === 'object' && !Array.isArray(stored)) saved = stored;
  } catch (error) { /* Storage may be unavailable inside a private browser frame. */ }
  let oldSelection = [];
  try { oldSelection = JSON.parse(sessionStorage.getItem(manualKey) || '[]'); } catch (error) {}
  const savedSelection = Array.isArray(saved.selection) ? saved.selection : oldSelection;
  const selection = new Set((Array.isArray(savedSelection) ? savedSelection : []).map(String).filter(no => horses.has(no)));
  const state = {
    sort: specs.has(saved.sort) ? saved.sort : 'no',
    direction: saved.direction === 'desc' ? 'desc' : 'asc',
    selectedOnly: saved.selectedOnly === true,
    filters: {},
    panels: saved.panels && typeof saved.panels === 'object' ? saved.panels : {},
    openHorse: horses.has(String(saved.openHorse)) ? String(saved.openHorse) : null,
    scrollLeft: Number.isFinite(saved.scrollLeft) && saved.scrollLeft >= 0 ? saved.scrollLeft : 0,
    scrollTop: Number.isFinite(saved.scrollTop) && saved.scrollTop >= 0 ? saved.scrollTop : 0,
  };
  if (saved.filters && typeof saved.filters === 'object') {
    for (const [key, filter] of Object.entries(saved.filters)) {
      if (!specs.has(key)) continue;
      try {
        const clean = cleanFilter(filter, specs.get(key));
        if (clean) state.filters[key] = clean;
      } catch (error) { /* Discard invalid stored UI conditions only. */ }
    }
  }

  function resize() {
    parent.postMessage({isStreamlitMessage: true, type: 'streamlit:setFrameHeight',
      height: Math.ceil(document.documentElement.getBoundingClientRect().height)}, '*');
  }
  function persist() {
    try {
      sessionStorage.setItem(stateKey, JSON.stringify({...state, selection: [...selection]}));
      sessionStorage.setItem(manualKey, JSON.stringify([...selection]));
    } catch (error) { /* Keep all controls working when browser storage is unavailable. */ }
  }
  function fieldValue(horse, key) {
    return key === 'user' ? selection.has(String(horse.no)) : (horse.values || {})[key];
  }
  function passes(horse, key, filter) {
    const spec = specs.get(key);
    return matchesFilter(fieldValue(horse, key), filter, spec, (horse.values || {})[spec.text_key]);
  }
  function detailFor(no) {
    return [...body.querySelectorAll('[data-detail-horse]')].find(detail => detail.dataset.detailHorse === no);
  }
  function filterDescription(key, filter) {
    const parts = [];
    if (filter.presence === 'missing') parts.push('未取得のみ');
    else {
      if (filter.presence === 'known') parts.push('取得済み');
      if (filter.min !== undefined) parts.push(filter.min + '以上');
      if (filter.max !== undefined) parts.push(filter.max + '以下');
      if (filter.text) parts.push('「' + filter.text + '」を含む');
      if (filter.choice) parts.push(filter.choice === 'selected' ? 'チェック済み' : filter.choice === 'unselected' ? '未チェック' : filter.choice);
    }
    return specs.get(key).label + '：' + parts.join('・');
  }
  function renderChips() {
    const host = byId('active-column-filters');
    host.replaceChildren();
    for (const [key, filter] of Object.entries(state.filters)) {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.removeFilter = key;
      button.textContent = filterDescription(key, filter) + ' ×';
      button.setAttribute('aria-label', filterDescription(key, filter) + 'の絞り込みを解除');
      host.appendChild(button);
    }
    const count = byId('filter-count');
    if (count) count.textContent = Object.keys(state.filters).length ? Object.keys(state.filters).length + '条件' : '条件なし';
  }
  function refresh() {
    const spec = specs.get(state.sort);
    const rows = [...body.querySelectorAll('tr[data-horse]')];
    rows.sort((a, b) => {
      const ah = horses.get(a.dataset.horse), bh = horses.get(b.dataset.horse);
      return compareValues(fieldValue(ah, state.sort), fieldValue(bh, state.sort), spec.type, state.direction)
        || compareValues(fieldValue(ah, 'no'), fieldValue(bh, 'no'), 'number', 'asc');
    });
    let visible = 0;
    for (const row of rows) {
      const no = row.dataset.horse, horse = horses.get(no), checked = selection.has(no);
      row.hidden = (state.selectedOnly && !checked)
        || Object.entries(state.filters).some(([key, filter]) => !passes(horse, key, filter));
      row.classList.toggle('user-selected', checked);
      const input = row.querySelector('[data-user-check]');
      if (input) input.checked = checked;
      const detail = detailFor(no);
      body.appendChild(row);
      if (detail) { detail.hidden = row.hidden; body.appendChild(detail); }
      if (!row.hidden) visible++;
    }
    byId('selection-count').textContent = '自分の✓ ' + selection.size + '頭 / 表示 ' + visible + '頭';
    byId('lineup-empty').hidden = visible > 0;
    byId('lineup-filter').value = state.selectedOnly ? 'selected' : 'all';
    byId('lineup-sort').value = state.sort;
    byId('lineup-direction').value = state.direction;
    document.querySelectorAll('th[data-column]').forEach(header => {
      const key = header.dataset.column;
      header.setAttribute('aria-sort', key === state.sort ? state.direction === 'asc' ? 'ascending' : 'descending' : 'none');
      const sortButton = header.querySelector('[data-column-sort]');
      if (sortButton) {
        sortButton.dataset.direction = key === state.sort ? state.direction : '';
        let indicator = sortButton.querySelector('.column-sort-indicator');
        if (!indicator) {
          indicator = document.createElement('span');
          indicator.className = 'column-sort-indicator';
          indicator.setAttribute('aria-hidden', 'true');
          sortButton.appendChild(indicator);
        }
        indicator.textContent = key === state.sort ? state.direction === 'asc' ? ' ↑' : ' ↓' : '';
      }
      const filterButton = header.querySelector('[data-column-filter]');
      if (filterButton) filterButton.dataset.active = String(Boolean(state.filters[key]));
    });
    renderChips();
    persist();
    resize();
  }
  const defaultDirection = key => ['score', 'ability', 'distance', 'course', 'average', 'maximum'].includes(key) ? 'desc' : 'asc';
  function sortBy(key, toggle = false) {
    if (!specs.has(key)) return;
    state.direction = toggle && state.sort === key ? state.direction === 'asc' ? 'desc' : 'asc' : defaultDirection(key);
    state.sort = key;
    refresh();
  }
  function renderEditor() {
    const spec = specs.get(byId('filter-column').value);
    if (!spec) return;
    const filter = state.filters[spec.key] || {};
    byId('filter-number-fields').hidden = !numericType(spec.type);
    byId('filter-text-fields').hidden = spec.type !== 'text' && !spec.text_key;
    byId('filter-choice-field').hidden = !['grade', 'boolean'].includes(spec.type);
    byId('filter-presence').value = filter.presence || 'all';
    byId('filter-min').value = filter.min ?? '';
    byId('filter-max').value = filter.max ?? '';
    byId('filter-text').value = filter.text || '';
    const choice = byId('filter-choice');
    choice.replaceChildren();
    const options = [['', '指定なし'], ...(spec.type === 'grade' ? ['A', 'B', 'C', 'D'].map(grade => [grade, grade])
      : [['selected', 'チェック済み'], ['unselected', '未チェック']])];
    for (const [value, label] of options) {
      const option = document.createElement('option'); option.value = value; option.textContent = label; choice.appendChild(option);
    }
    choice.value = filter.choice || '';
    if (byId('column-filter-error')) byId('column-filter-error').textContent = '';
  }
  byId('lineup-sort').addEventListener('change', event => sortBy(event.target.value));
  byId('lineup-direction').addEventListener('change', event => {state.direction = event.target.value === 'desc' ? 'desc' : 'asc'; refresh();});
  byId('lineup-filter').addEventListener('change', event => {state.selectedOnly = event.target.value === 'selected'; refresh();});
  document.querySelectorAll('[data-column-sort]').forEach(button => button.addEventListener('click', () => sortBy(button.dataset.columnSort, true)));
  document.querySelectorAll('[data-column-filter]').forEach(button => button.addEventListener('click', () => {
    byId('lineup-filters').open = true;
    byId('filter-column').value = button.dataset.columnFilter;
    renderEditor();
    byId('lineup-filters').scrollIntoView({block: 'nearest'});
  }));
  document.querySelectorAll('[data-user-check]').forEach(input => input.addEventListener('change', () => {
    const no = input.dataset.userCheck;
    if (!horses.has(no)) return;
    if (input.checked) selection.add(no); else selection.delete(no);
    refresh();
  }));
  byId('clear-user-selection').addEventListener('click', () => {selection.clear(); refresh();});
  byId('filter-column').addEventListener('change', renderEditor);
  byId('add-column-filter').addEventListener('click', () => {
    const key = byId('filter-column').value;
    try {
      const filter = cleanFilter({presence: byId('filter-presence').value, min: byId('filter-min').value,
        max: byId('filter-max').value, text: byId('filter-text').value, choice: byId('filter-choice').value}, specs.get(key));
      if (filter) state.filters[key] = filter; else delete state.filters[key];
      if (byId('column-filter-error')) byId('column-filter-error').textContent = '';
      refresh();
    } catch (error) {
      if (!(error instanceof RangeError)) throw error;
      if (byId('column-filter-error')) byId('column-filter-error').textContent = error.message;
    }
  });
  for (const id of ['filter-min', 'filter-max', 'filter-text'])
    byId(id).addEventListener('keydown', event => {if (event.key === 'Enter') {event.preventDefault(); byId('add-column-filter').click();}});
  byId('active-column-filters').addEventListener('click', event => {
    const button = event.target.closest('[data-remove-filter]');
    if (button) {delete state.filters[button.dataset.removeFilter]; refresh(); renderEditor();}
  });
  byId('clear-column-filters').addEventListener('click', () => {
    state.filters = {}; state.selectedOnly = false; refresh(); renderEditor();
  });
  document.querySelectorAll('details[data-persist-panel]').forEach(panel => {
    if (typeof state.panels[panel.id] === 'boolean') panel.open = state.panels[panel.id];
    panel.addEventListener('toggle', () => {state.panels[panel.id] = panel.open; persist(); resize();});
  });
  const saveScroll = () => {state.scrollLeft = tableScroll.scrollLeft; state.scrollTop = tableScroll.scrollTop; persist();};
  tableScroll.addEventListener('scroll', saveScroll, {passive: true});
  window.addEventListener('pagehide', saveScroll);
  window.keibaComparison = {
    has: no => selection.has(String(no)),
    getOpenHorse: () => state.openHorse,
    setOpenHorse: no => {state.openHorse = horses.has(String(no)) ? String(no) : null; persist();},
    prepareOpen: no => {
      const horse = horses.get(String(no));
      if (!horse) return;
      if (state.selectedOnly && !selection.has(String(no))) state.selectedOnly = false;
      for (const [key, filter] of Object.entries(state.filters))
        if (!passes(horse, key, filter)) delete state.filters[key];
      refresh();
    },
    refresh,
    dispose: () => {disposed = true; window.removeEventListener('pagehide', saveScroll);},
  };
  renderEditor();
  refresh();
  // The existing shared-detail listener is installed by the following script.
  setTimeout(() => {
    if (disposed) return;
    if (state.openHorse) document.dispatchEvent(new CustomEvent('keiba:restore-detail', {detail: {no: state.openHorse}}));
    requestAnimationFrame(() => {
      tableScroll.scrollLeft = state.scrollLeft;
      tableScroll.scrollTop = state.scrollTop;
      resize();
    });
  }, 0);
})();

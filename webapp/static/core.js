// core.js - shared state, API client, dialogs and reusable UI components.
"use strict";
const { createApp, reactive, ref, computed, watch, onMounted, onBeforeUnmount, nextTick } = Vue;
const L = window.Logic;

// ------------------------------------------------------------------ helpers
const pad2 = (n) => String(n).padStart(2, "0");
// datetime.now().strftime('%d-%m-%y')
function todayStr(d) { d = d || new Date(); return pad2(d.getDate()) + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getFullYear() % 100); }
// datetime.now().strftime('%I:%M %p')
function nowTimeStr(d) {
  d = d || new Date();
  let h = d.getHours();
  const ap = h >= 12 ? "PM" : "AM";
  h = h % 12; if (h === 0) h = 12;
  return pad2(h) + ":" + pad2(d.getMinutes()) + " " + ap;
}
function daysAgoStr(n) { const d = new Date(); d.setDate(d.getDate() - n); return todayStr(d); }
function parseDmy(s) {
  const m = /^(\d{1,2})-(\d{1,2})-(\d{2})$/.exec(String(s || "").trim());
  if (!m) return null;
  let y = parseInt(m[3], 10); y += y <= 68 ? 2000 : 1900;
  const d = new Date(y, parseInt(m[2], 10) - 1, parseInt(m[1], 10));
  if (d.getMonth() !== parseInt(m[2], 10) - 1) return null;
  return d;
}
function debounce(fn, ms) {
  let t = null;
  const wrapped = (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  wrapped.cancel = () => clearTimeout(t);
  return wrapped;
}
const hasStar = (name) => typeof name === "string" && name.endsWith(" ⭐");
const stripStar = (name) => hasStar(name) ? name.slice(0, -2) : name;

// ------------------------------------------------------------------ global state
const store = reactive({
  phase: "login",          // login | booting | app | fatal
  fatal: "",
  isOwner: false,
  materials: [],
  tab: "billing",
  version: 0,              // bumped by reloadAll(); pages reload when it changes
  busy: 0,
  status: "Records: Loading...",
  theme: document.documentElement.getAttribute("data-theme") || "light",
});
const materialMap = new Map();
function setMaterials(list) {
  store.materials = list;
  materialMap.clear();
  for (const m of list) materialMap.set(m.code, m);
}
// materials.get_material_by_code
function materialByCode(code) {
  if (!code) return null;
  return materialMap.get(L.materialKey(code)) || null;
}

const bus = {
  handlers: {},
  on(evt, fn) { (this.handlers[evt] = this.handlers[evt] || []).push(fn); },
  off(evt, fn) { this.handlers[evt] = (this.handlers[evt] || []).filter((f) => f !== fn); },
  emit(evt, ...args) { for (const fn of this.handlers[evt] || []) fn(...args); },
};
// Same idea as callbacks.reload_all_tabs(): every page refreshes its data.
function reloadAll() { store.version++; refreshStatus(); }

// ------------------------------------------------------------------ API
class ApiError extends Error {
  constructor(err) { super(err.message); this.title = err.title || "Error"; this.kind = err.kind || "error"; }
}
async function api(method, params) {
  const res = await fetch("/api/" + method, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-App-Token": window.APP_TOKEN },
    body: JSON.stringify(params || {}),
  });
  if (!res.ok) throw new ApiError({ title: "Connection Error", message: "The app could not reach its local service (" + res.status + ")." });
  const data = await res.json();
  if (!data.ok) throw new ApiError(data.error);
  return data.result;
}
const FAIL = Symbol("fail");
// Calls the API and shows any error as a dialog. Returns FAIL on error.
async function run(method, params, opts) {
  store.busy++;
  try {
    return await api(method, params);
  } catch (e) {
    if (!(opts && opts.quiet)) await alertBox(e.kind || "error", e.title || "Error", e.message || String(e));
    return FAIL;
  } finally {
    store.busy--;
  }
}
async function refreshStatus() {
  try { store.status = (await api("status")).text; } catch (e) { /* ignore */ }
}

// ------------------------------------------------------------------ dialogs & toasts
const dialogs = reactive([]);
let dialogSeq = 0;
function openDialog(d) {
  return new Promise((resolve) => { dialogs.push(Object.assign({ id: ++dialogSeq, resolve }, d)); });
}
function closeDialog(d, value) {
  const i = dialogs.indexOf(d);
  if (i >= 0) dialogs.splice(i, 1);
  d.resolve(value);
}
function alertBox(kind, title, message) { return openDialog({ type: "alert", kind, title, message }); }
function confirmBox(title, message, opts) {
  return openDialog(Object.assign({ type: "confirm", kind: "question", title, message, okText: "Yes", cancelText: "No" }, opts || {}));
}
// fields: [{key, label, type: text|textarea|checkbox, required, placeholder, value, disabled, numeric}]
function formBox(opts) {
  const values = {};
  for (const f of opts.fields) values[f.key] = f.value !== undefined ? f.value : (f.type === "checkbox" ? false : "");
  return openDialog(Object.assign({ type: "form", values, error: "", okText: "OK" }, opts));
}

const toasts = reactive([]);
let toastSeq = 0;
function toast(kind, title, message, ms) {
  const t = { id: ++toastSeq, kind, title, message };
  toasts.push(t);
  const life = ms !== undefined ? ms : (kind === "error" ? 0 : 6000);
  if (life) setTimeout(() => dismissToast(t), life);
}
function dismissToast(t) { const i = toasts.indexOf(t); if (i >= 0) toasts.splice(i, 1); }

// ------------------------------------------------------------------ icons
const ICONS = {
  receipt: '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 17.5v-11"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
  wallet: '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
  calendar: '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
  usersearch: '<circle cx="10" cy="7" r="4"/><path d="M10.3 15H7a4 4 0 0 0-4 4v2"/><circle cx="17" cy="17" r="3"/><path d="m21 21-1.9-1.9"/>',
  chart: '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  wrench: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
  package: '<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/><path d="M12 22V12"/><path d="m3.3 7 7.703 4.734a2 2 0 0 0 1.994 0L20.7 7"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  printer: '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6"/><rect x="6" y="14" width="12" height="8" rx="1"/>',
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  minus: '<path d="M5 12h14"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>',
  cloud: '<path d="M12 13v8"/><path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/><path d="m8 17 4-4 4 4"/>',
  edit: '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>',
  save: '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>',
  eraser: '<path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 5.6c1 1 1 2.5 0 3.4L13 21"/><path d="M22 21H7"/><path d="m5 11 9 9"/>',
  file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
  ban: '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
  scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  power: '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/>',
  left: '<path d="m15 18-6-6 6-6"/>',
  right: '<path d="m9 18 6-6-6-6"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
  scissors: '<circle cx="6" cy="6" r="3"/><path d="M8.12 8.12 12 12"/><path d="M20 4 8.12 15.88"/><circle cx="6" cy="18" r="3"/><path d="M14.8 14.8 20 20"/>',
  lock: '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
  alert: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
  ok: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
  warn: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  help: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
  trend: '<path d="M16 7h6v6"/><path d="m22 7-8.5 8.5-5-5L2 17"/>',
  arrowIn: '<path d="M17 7 7 17"/><path d="M17 17H7V7"/>',
  arrowOut: '<path d="M7 7h10v10"/><path d="M7 17 17 7"/>',
  phone: '<rect width="14" height="20" x="5" y="2" rx="2" ry="2"/><path d="M12 18h.01"/>',
  cash: '<rect width="20" height="12" x="2" y="6" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01M18 12h.01"/>',
  trophy: '<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/>',
  history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
  user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  layers: '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
  flame: '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
};
const Icon = {
  props: { name: String, size: String },
  computed: { paths() { return ICONS[this.name] || ""; } },
  template: '<svg class="icon" :class="size" viewBox="0 0 24 24" aria-hidden="true" v-html="paths"></svg>',
};

// ------------------------------------------------------------------ DatePicker (CustomDatePicker port)
const DatePicker = {
  components: { Icon },
  props: { modelValue: String, placeholder: { type: String, default: "Any date" }, clearable: Boolean, disabled: Boolean, small: Boolean, iconOnly: Boolean },
  emits: ["update:modelValue", "change"],
  setup(props, { emit }) {
    const open = ref(false), btn = ref(null), pop = ref(null);
    const view = reactive({ y: 0, m: 0 });
    const pos = reactive({ top: 0, left: 0 });
    const toggle = () => {
      if (props.disabled) return;
      if (open.value) { open.value = false; return; }
      const cur = parseDmy(props.modelValue) || new Date();
      view.y = cur.getFullYear(); view.m = cur.getMonth();
      const r = btn.value.getBoundingClientRect();
      let left = r.left, top = r.bottom + 6;
      if (left + 290 > window.innerWidth) left = window.innerWidth - 298;
      if (top + 340 > window.innerHeight) top = Math.max(8, r.top - 346);
      pos.top = top; pos.left = left;
      open.value = true;
    };
    const monthName = computed(() => new Date(view.y, view.m, 1).toLocaleString("en-US", { month: "long" }) + " " + view.y);
    const cells = computed(() => {
      const first = new Date(view.y, view.m, 1);
      const lead = (first.getDay() + 6) % 7; // Monday first, like calendar.monthcalendar
      const days = new Date(view.y, view.m + 1, 0).getDate();
      const out = [];
      for (let i = 0; i < lead; i++) out.push(null);
      for (let d = 1; d <= days; d++) out.push(d);
      return out;
    });
    const sel = computed(() => parseDmy(props.modelValue));
    const isSel = (d) => sel.value && sel.value.getFullYear() === view.y && sel.value.getMonth() === view.m && sel.value.getDate() === d;
    const isToday = (d) => { const t = new Date(); return t.getFullYear() === view.y && t.getMonth() === view.m && t.getDate() === d; };
    const shift = (n) => { let m = view.m + n, y = view.y; if (m < 0) { m = 11; y--; } if (m > 11) { m = 0; y++; } view.m = m; view.y = y; };
    const pick = (d) => { const v = todayStr(new Date(view.y, view.m, d)); emit("update:modelValue", v); emit("change", v); open.value = false; };
    const clear = () => { emit("update:modelValue", ""); emit("change", ""); open.value = false; };
    const today = () => { const v = todayStr(); emit("update:modelValue", v); emit("change", v); open.value = false; };
    const onDoc = (e) => { if (open.value && pop.value && !pop.value.contains(e.target) && !btn.value.contains(e.target)) open.value = false; };
    const onScroll = (e) => { if (open.value && pop.value && !pop.value.contains(e.target)) open.value = false; };
    onMounted(() => { document.addEventListener("mousedown", onDoc); window.addEventListener("scroll", onScroll, true); window.addEventListener("resize", onScroll); });
    onBeforeUnmount(() => { document.removeEventListener("mousedown", onDoc); window.removeEventListener("scroll", onScroll, true); window.removeEventListener("resize", onScroll); });
    return { open, btn, pop, pos, toggle, monthName, cells, isSel, isToday, shift, pick, clear, today };
  },
  template: `
  <div class="dp">
    <button ref="btn" type="button" class="btn" :class="[iconOnly ? 'icon-only' : 'dp-btn', small ? 'sm' : '']" :disabled="disabled" @click="toggle" :title="iconOnly ? 'Pick a date' : ''">
      <Icon name="calendar" size="sm"/>
      <template v-if="!iconOnly">
        <span v-if="modelValue" class="num">{{ modelValue }}</span><span v-else class="placeholder">{{ placeholder }}</span>
      </template>
    </button>
    <teleport to="body">
      <div v-if="open" ref="pop" class="dp-pop" :style="{ top: pos.top + 'px', left: pos.left + 'px' }">
        <div class="dp-head">
          <button class="btn ghost sm icon-only" @click="shift(-1)"><Icon name="left" size="sm"/></button>
          <span class="dp-title">{{ monthName }}</span>
          <button class="btn ghost sm icon-only" @click="shift(1)"><Icon name="right" size="sm"/></button>
        </div>
        <div class="dp-grid">
          <div class="dp-dow" v-for="d in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']" :key="d">{{ d }}</div>
          <template v-for="(d, i) in cells" :key="i">
            <div v-if="!d"></div>
            <button v-else class="dp-day" :class="{ sel: isSel(d), today: isToday(d) }" @click="pick(d)">{{ d }}</button>
          </template>
        </div>
        <div class="dp-foot">
          <button class="btn ghost sm" @click="today">Today</button>
          <button v-if="clearable" class="btn ghost sm" @click="clear">Clear</button>
        </div>
      </div>
    </teleport>
  </div>`,
};

// ------------------------------------------------------------------ Segmented control (radio buttons)
const Seg = {
  props: { modelValue: [String, Number], options: Array, disabled: Boolean },
  emits: ["update:modelValue", "change"],
  methods: { set(v) { if (this.disabled || v === this.modelValue) return; this.$emit("update:modelValue", v); this.$emit("change", v); } },
  template: `
  <div class="seg" role="radiogroup">
    <button v-for="o in options" :key="o.value" type="button" :class="{ on: o.value === modelValue }" :disabled="disabled" @click="set(o.value)">
      <span v-if="o.dot" class="dot" :style="{ background: o.dot }"></span>{{ o.label }}
    </button>
  </div>`,
};

// ------------------------------------------------------------------ DataTable (virtualised for large lists)
const ROW_H = 38;
const DataTable = {
  components: { Icon },
  props: {
    columns: Array, rows: Array, rowKey: Function, selectedKey: [String, Number, null],
    rowClass: Function, selectable: Boolean, emptyText: { type: String, default: "No records to show." },
    emptyIcon: { type: String, default: "search" }, minWidth: String,
  },
  emits: ["select", "activate"],
  setup(props) {
    const wrap = ref(null);
    const scrollTop = ref(0), height = ref(600);
    const virtual = computed(() => props.rows.length > 120);
    const range = computed(() => {
      if (!virtual.value) return [0, props.rows.length];
      const start = Math.max(0, Math.floor(scrollTop.value / ROW_H) - 10);
      const end = Math.min(props.rows.length, Math.ceil((scrollTop.value + height.value) / ROW_H) + 10);
      return [start, end];
    });
    const visible = computed(() => props.rows.slice(range.value[0], range.value[1]).map((row, i) => ({ row, index: range.value[0] + i })));
    const topPad = computed(() => range.value[0] * ROW_H);
    const bottomPad = computed(() => (props.rows.length - range.value[1]) * ROW_H);
    const onScroll = () => { scrollTop.value = wrap.value.scrollTop; };
    let ro = null;
    onMounted(() => {
      height.value = wrap.value.clientHeight || 600;
      ro = new ResizeObserver(() => { if (wrap.value) height.value = wrap.value.clientHeight || 600; });
      ro.observe(wrap.value);
    });
    onBeforeUnmount(() => { if (ro) ro.disconnect(); });
    watch(() => props.rows, () => { if (wrap.value && wrap.value.scrollTop > props.rows.length * ROW_H) { wrap.value.scrollTop = 0; scrollTop.value = 0; } });
    const cell = (col, row) => col.get ? col.get(row) : (row.values ? row.values[col.idx] : row[col.key]);
    const key = (row, index) => props.rowKey ? props.rowKey(row, index) : index;
    return { wrap, onScroll, visible, topPad, bottomPad, cell, key };
  },
  template: `
  <div class="table-wrap" ref="wrap" @scroll="onScroll">
    <table class="data" :class="{ selectable }" :style="minWidth ? { minWidth } : null">
      <thead><tr>
        <th v-for="c in columns" :key="c.label" :class="c.align" :style="c.width ? { width: c.width } : null">{{ c.label }}</th>
      </tr></thead>
      <tbody>
        <tr v-if="topPad" class="spacer-row"><td :colspan="columns.length" :style="{ height: topPad + 'px' }"></td></tr>
        <tr v-for="v in visible" :key="key(v.row, v.index)"
            :class="[rowClass ? rowClass(v.row) : '', { selected: selectedKey !== null && selectedKey !== undefined && key(v.row, v.index) === selectedKey }]"
            @click="$emit('select', v.row)" @dblclick="$emit('activate', v.row)">
          <td v-for="c in columns" :key="c.label" :class="[c.align, c.cls ? c.cls(v.row) : '']" :title="c.title === false ? null : String(cell(c, v.row) ?? '')">
            <slot :name="'cell-' + (c.key || c.idx)" :row="v.row" :value="cell(c, v.row)">{{ cell(c, v.row) }}</slot>
          </td>
        </tr>
        <tr v-if="bottomPad" class="spacer-row"><td :colspan="columns.length" :style="{ height: bottomPad + 'px' }"></td></tr>
      </tbody>
    </table>
    <div v-if="!rows.length" class="empty"><Icon :name="emptyIcon"/><div>{{ emptyText }}</div></div>
  </div>`,
};

// ------------------------------------------------------------------ Stat card
const Stat = {
  components: { Icon },
  props: { label: String, value: [String, Number], icon: String, tone: { type: String, default: "indigo" }, small: Boolean },
  template: `
  <div class="stat" :class="'tone-' + tone">
    <div class="stat-top"><span class="stat-icon"><Icon :name="icon" size="sm"/></span><span>{{ label }}</span><span class="stat-extra"><slot name="extra"/></span></div>
    <div class="stat-value" :class="{ small }" :title="String(value)">{{ value }}</div>
    <slot/>
  </div>`,
};

// Keeps a page's data in step with reloadAll(): reloads now if the page is
// visible, otherwise the next time it is opened.
function useReload(props, load) {
  let stale = !props.active;
  watch(() => store.version, () => { if (props.active) load(); else stale = true; });
  watch(() => props.active, (a) => { if (a && stale) { stale = false; load(); } });
  onMounted(() => { if (props.active) load(); });
}

const Search = {
  components: { Icon },
  props: { modelValue: String, placeholder: { type: String, default: "Search" }, width: { type: String, default: "260px" } },
  emits: ["update:modelValue"],
  template: `
  <div class="input-group" :style="{ width }">
    <Icon name="search" size="sm"/>
    <input class="input" :value="modelValue" :placeholder="placeholder" @input="$emit('update:modelValue', $event.target.value)">
    <button v-if="modelValue" class="btn ghost sm icon-only clear-x" title="Clear" @click="$emit('update:modelValue', '')"><Icon name="x" size="sm"/></button>
  </div>`,
};

window.Core = { store, api, run, FAIL, reloadAll, refreshStatus, bus, dialogs, closeDialog, alertBox, confirmBox, formBox,
  toasts, toast, dismissToast, Icon, DatePicker, Seg, DataTable, Stat, Search, useReload, todayStr, nowTimeStr, daysAgoStr,
  debounce, setMaterials, materialByCode, hasStar, stripStar };

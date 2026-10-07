// app.js - login, app shell (sidebar / top bar), dialogs, shortcuts.
"use strict";

const TABS = [
  { id: "billing", label: "Outward Billing", icon: "receipt", title: "Outward Billing", sub: "Create bills, look up records and process returns" },
  { id: "pending_returns", label: "Pending Returns", icon: "undo", title: "Pending Returns", sub: "Customers who still have items out" },
  { id: "pending", label: "Pending / Refunds", icon: "wallet", title: "Pending / Refunds", sub: "Balances to collect and refunds to give" },
  { id: "daily", label: "Day's Overview", icon: "calendar", title: "Day's Overview", sub: "Everything that happened in a date range" },
  { id: "customer_report", label: "Customer Report", icon: "usersearch", title: "Customer Report", sub: "Full billing history for one customer" },
  { id: "analytics", label: "Analytics", icon: "chart", title: "Analytics", sub: "Pending amounts, cash flow, stock and top customers" },
  { id: "customers", label: "Customers", icon: "users", title: "Customers", sub: "Customer directory" },
  { id: "equipment", label: "Equipment Analytics", icon: "wrench", title: "Equipment Analytics", sub: "Revenue by equipment type", owner: true },
  { id: "team", label: "Team & Branches", icon: "users", title: "Team & Branches", sub: "Cashier logins and each branch's sync status", owner: true },
];

// ------------------------------------------------------------------ dialog host
const DialogHost = {
  components: { Icon },
  directives: {
    // focus the first field (or the main button) once, when the dialog opens
    dlgfocus: { mounted(el) { nextTick(() => { const t = el.querySelector("[data-autofocus]") || el.querySelector(".modal-foot .btn.primary, .modal-foot .btn.danger-solid"); if (t) t.focus(); }); } },
  },
  setup() {
    const busy = ref(false);
    const iconFor = (k) => ({ info: "alert", success: "ok", warning: "warn", error: "alert", danger: "warn", question: "help" }[k] || "alert");
    async function ok(d) {
      if (d.type === "alert") return closeDialog(d, true);
      if (d.type === "confirm") return closeDialog(d, true);
      if (busy.value) return;
      const err = d.validate ? d.validate(d.values) : null;
      d.error = err || "";
      if (err) return;
      if (d.onSubmit) {
        busy.value = true;
        try { const res = await d.onSubmit(d.values); if (res === false) return; }
        finally { busy.value = false; }
      }
      closeDialog(d, d.values);
    }
    function cancel(d) {
      if (busy.value) return;
      closeDialog(d, d.type === "confirm" ? false : (d.type === "form" ? null : true));
    }
    function onKey(e) {
      const d = dialogs[dialogs.length - 1];
      if (!d) return;
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancel(d); }
      else if (e.key === "Enter" && !(e.target && (e.target.tagName === "TEXTAREA" || e.target.tagName === "BUTTON"))) { e.preventDefault(); e.stopPropagation(); ok(d); }
    }
    onMounted(() => window.addEventListener("keydown", onKey, true));
    onBeforeUnmount(() => window.removeEventListener("keydown", onKey, true));
    return { dialogs, ok, cancel, iconFor, busy };
  },
  template: `
  <div v-for="d in dialogs" :key="d.id" class="overlay" @mousedown.self="d.type !== 'form' && cancel(d)">
    <div class="modal" :class="{ wide: d.wide }" v-dlgfocus role="dialog" aria-modal="true">
      <template v-if="d.type !== 'form'">
        <div class="modal-body">
          <div class="modal-icon" :class="d.kind"><Icon :name="iconFor(d.kind)" size="lg"/></div>
          <div><h2>{{ d.title }}</h2><p>{{ d.message }}</p></div>
        </div>
        <div class="modal-foot">
          <button v-if="d.type === 'confirm'" class="btn" @click="cancel(d)">{{ d.cancelText }}</button>
          <button class="btn" :class="d.kind === 'danger' ? 'danger-solid' : 'primary'" @click="ok(d)">{{ d.type === 'confirm' ? d.okText : 'OK' }}</button>
        </div>
      </template>
      <template v-else>
        <div class="modal-form">
          <div style="display:flex;align-items:center;gap:12px">
            <div class="modal-icon question"><Icon :name="d.icon || 'edit'" size="lg"/></div>
            <h2>{{ d.title }}</h2>
          </div>
          <div v-for="(fl, i) in d.fields" :key="fl.key" class="field">
            <label v-if="fl.type !== 'checkbox'">{{ fl.label }}<span v-if="fl.required" class="req">*</span></label>
            <textarea v-if="fl.type === 'textarea'" class="textarea" rows="3" v-model="d.values[fl.key]" :disabled="fl.disabled" :data-autofocus="fl.autofocus ? '' : null"></textarea>
            <label v-else-if="fl.type === 'checkbox'" class="check"><input type="checkbox" v-model="d.values[fl.key]">{{ fl.label }}</label>
            <select v-else-if="fl.type === 'select'" class="select" v-model="d.values[fl.key]" :disabled="fl.disabled">
              <option v-for="o in fl.options" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
            <input v-else-if="fl.type === 'password'" class="input" type="password" v-model="d.values[fl.key]" autocomplete="new-password" :data-autofocus="fl.autofocus ? '' : null">
            <input v-else class="input" :class="{ num: fl.numeric }" v-model="d.values[fl.key]" :disabled="fl.disabled" :inputmode="fl.numeric ? 'decimal' : null" :data-autofocus="fl.autofocus ? '' : null">
          </div>
          <div v-if="d.note" class="t-muted" style="font-size:12.5px">{{ d.note }}</div>
          <div v-if="d.error" class="form-error">{{ d.error }}</div>
        </div>
        <div class="modal-foot">
          <button class="btn" :disabled="busy" @click="cancel(d)">Cancel</button>
          <button class="btn primary" :disabled="busy" @click="ok(d)">{{ busy ? 'Saving…' : d.okText }}</button>
        </div>
      </template>
    </div>
  </div>`,
};

const ToastHost = {
  components: { Icon },
  setup() {
    const iconFor = (k) => ({ info: "cloud", success: "ok", error: "alert", warning: "warn" }[k] || "alert");
    return { toasts, dismissToast, iconFor };
  },
  template: `
  <div class="toasts">
    <div v-for="t in toasts" :key="t.id" class="toast">
      <div class="modal-icon" :class="t.kind"><Icon :name="iconFor(t.kind)" size="sm"/></div>
      <div style="min-width:0"><div class="t-title">{{ t.title }}</div><div class="t-msg">{{ t.message }}</div></div>
      <button class="btn ghost sm icon-only x" @click="dismissToast(t)"><Icon name="x" size="sm"/></button>
    </div>
  </div>`,
};

// ------------------------------------------------------------------ login (cloud accounts, works offline after first sign-in)
const LoginView = {
  components: { Icon },
  setup() {
    const user = ref(""), pwd = ref(""), error = ref(""), shake = ref(false), working = ref(false);
    const userInput = ref(null), pwdInput = ref(null);
    const branchPick = reactive({ open: false, branches: {}, value: "", phone: false });
    let lastUser = "";
    try { lastUser = localStorage.getItem("last_user") || ""; } catch (e) { /* ignore */ }
    user.value = lastUser;
    async function submit(branch) {
      if (working.value) return;
      working.value = true; error.value = "";
      try {
        const r = await api("login", { username: user.value, password: pwd.value, branch: branch || null });
        if (r.choose_branch) {
          let last = ""; try { last = localStorage.getItem("last_branch") || ""; } catch (e) { /* ignore */ }
          branchPick.branches = r.branches; branchPick.phone = !!r.phone;
          branchPick.value = (last && r.branches[last]) ? last : (r.suggested || Object.keys(r.branches)[0]);
          branchPick.open = true; store.branches = r.branches;
          return;
        }
        try { localStorage.setItem("last_branch", r.branch); } catch (e) { /* ignore */ }
        try { localStorage.setItem("last_user", user.value.trim().toLowerCase()); } catch (e) { /* ignore */ }
        store.user = r; store.isOwner = r.role === "owner";
        await boot();
        if (r.first_setup) toast("success", "Computer set up", `This computer is now the ${r.branch_name} (${r.branch}) counter.` + (r.restored ? ` Downloaded ${r.restored} bills from the cloud.` : "") + " Its data syncs to the cloud automatically.", 10000);
        else if (r.offline) toast("warning", "Signed in offline", "No internet right now. Keep working normally; everything will upload when the connection is back.", 9000);
      } catch (e) {
        error.value = e.message || "Sign in failed";
        pwd.value = "";
        shake.value = true; setTimeout(() => (shake.value = false), 400);
        nextTick(() => pwdInput.value && pwdInput.value.focus());
      } finally { working.value = false; }
    }
    const exit = () => api("quit").catch(() => {});
    onMounted(() => { (lastUser ? pwdInput.value : userInput.value)?.focus(); });
    return { user, pwd, error, shake, working, userInput, pwdInput, branchPick, submit, exit, isWeb: IS_WEB };
  },
  template: `
  <div class="login">
    <form v-if="!branchPick.open" class="login-card" :class="{ shake }" @submit.prevent="submit()">
      <div class="brand-mark"><Icon name="receipt"/></div>
      <h1>Rental Billing</h1>
      <p class="lead">Sign in with your username and password.</p>
      <div class="field">
        <label>Username</label>
        <input ref="userInput" class="input" v-model="user" autocomplete="username" autocapitalize="off" spellcheck="false" placeholder="e.g. ravi">
      </div>
      <div class="field" style="margin-top:12px">
        <label>Password</label>
        <input ref="pwdInput" class="input" type="password" v-model="pwd" autocomplete="current-password" placeholder="••••••••">
      </div>
      <div v-if="error" class="form-error" style="margin-top:10px;white-space:pre-line">{{ error }}</div>
      <button class="btn primary" type="submit" :disabled="working">{{ working ? 'Signing in…' : 'Sign in' }}</button>
      <div class="login-foot"><span>{{ isWeb ? 'v2.0 · All branches' : 'v2.0 · Works offline after first sign-in' }}</span><button v-if="!isWeb" type="button" class="btn ghost sm" @click="exit"><Icon name="power" size="sm"/>Exit</button></div>
    </form>
    <div v-else class="login-card">
      <div class="brand-mark"><Icon name="layers"/></div>
      <h1>{{ branchPick.phone ? 'Open a branch' : 'Set up this computer' }}</h1>
      <p v-if="branchPick.phone" class="lead">Which branch do you want to work on? You can switch later from the menu. Bills made here are numbered in the branch's phone series.</p>
      <p v-else class="lead">This is the first sign-in on this computer. Which branch's counter is it? Its bills will be numbered and synced for that branch.</p>
      <div class="branch-pick">
        <label v-for="(name, code) in branchPick.branches" :key="code" class="branch-opt" :class="{ on: branchPick.value === code }">
          <input type="radio" :value="code" v-model="branchPick.value">
          <span><b>{{ name }}</b><small>{{ branchPick.phone ? 'Phone bills: ' + code + '-M0001…' : 'Bills: ' + code + '-A0001…' }}</small></span>
        </label>
      </div>
      <div v-if="error" class="form-error" style="margin-top:10px">{{ error }}</div>
      <button class="btn primary" :disabled="working || !branchPick.value" @click="submit(branchPick.value)">
        <template v-if="branchPick.phone">{{ working ? 'Opening… (the first time can take a minute)' : 'Open branch' }}</template><template v-else>{{ working ? 'Downloading this branch’s data… (can take a minute)' : 'Use this branch' }}</template></button>
      <div class="login-foot"><span>{{ branchPick.phone ? '' : "You can't change this later from the app." }}</span><button type="button" class="btn ghost sm" @click="branchPick.open = false">Back</button></div>
    </div>
  </div>`,
};

async function boot() {
  store.phase = "booting";
  try {
    const r = await api("init");
    store.isOwner = r.is_owner;
    if (r.user) store.user = r.user;
    setMaterials(r.materials);
    store.phase = "app";
    refreshStatus();
    if (r.warning) await alertBox("warning", "Database Issue", r.warning);
  } catch (e) {
    store.fatal = e.message;
    store.phase = "fatal";
  }
}

// ------------------------------------------------------------------ shell
const Shell = {
  components: Object.assign({ Icon, BillingPage: window.BillingPage }, window.Pages),
  setup() {
    const tabs = computed(() => TABS.filter((t) => !t.owner || store.isOwner));
    const current = computed(() => TABS.find((t) => t.id === store.tab) || TABS[0]);
    const visited = reactive({ billing: true });
    watch(() => store.tab, (t) => { visited[t] = true; }, { immediate: true });
    const toggleTheme = () => {
      store.theme = store.theme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", store.theme);
      try { localStorage.setItem("theme", store.theme); } catch (e) { /* ignore */ }
    };
    const syncTone = computed(() => !sync.online ? "off" : (sync.error ? "warn" : (sync.pending || sync.running ? "busy" : "ok")));
    const syncLabel = computed(() => !sync.online ? "Offline" : (sync.error ? "Sync problem" : (sync.pending ? "Syncing…" : "Synced")));
    const syncSub = computed(() => {
      if (sync.pending) return `${sync.pending} change${sync.pending === 1 ? "" : "s"} waiting`;
      return sync.last_sync ? "Last: " + sync.last_sync.replace(/:\d\d (AM|PM)$/, " $1") : "Not synced yet";
    });
    const syncTitle = computed(() => sync.error ? sync.error + " — click to retry" : "Click to sync now");
    const syncNow = () => api("sync_now").then(() => setTimeout(pollSync, 1500)).catch(() => {});
    async function switchBranch(code) {
      if (!store.user || code === store.user.branch) return;
      store.navOpen = false;
      const r = await run("switch_branch", { branch: code });
      if (r === FAIL) return;
      try { localStorage.setItem("last_branch", code); } catch (e) { /* ignore */ }
      store.user = r;
      await boot();
      reloadAll();
      if (window.BillingActions) window.BillingActions.clear();
      toast("success", "Branch opened", `Now showing ${r.branch_name}.`);
    }
    return { store, tabs, current, visited, toggleTheme, manualRefresh, quickBackup, requestQuit, signOut, switchBranch, isWeb: IS_WEB,
             syncTone, syncLabel, syncSub, syncTitle, syncNow };
  },
  template: `
  <div class="shell" :class="{ 'nav-open': store.navOpen }">
    <div class="nav-scrim" @click="store.navOpen = false"></div>
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><Icon name="receipt"/></div>
        <div class="brand-text"><div class="brand-name">{{ store.user ? store.user.branch_name : 'Rental Billing' }}</div><div class="brand-sub">{{ store.user ? store.user.display_name : '' }} · {{ store.isOwner ? 'Owner' : 'Cashier' }}</div></div>
      </div>
      <nav class="nav">
        <div class="nav-label">Workspace</div>
        <button v-for="t in tabs" :key="t.id" class="nav-item" :class="{ active: store.tab === t.id }" @click="store.tab = t.id; store.navOpen = false" :title="t.label">
          <Icon :name="t.icon"/><span>{{ t.label }}</span><em v-if="t.owner" class="badge-owner" title="Owner only"><Icon name="lock" size="sm"/></em>
        </button>
      </nav>
      <div class="sidebar-foot">
        <button class="sync-pill" :class="syncTone" @click="syncNow" :title="syncTitle">
          <span class="sync-dot"></span><span class="sync-text"><b>{{ syncLabel }}</b><small>{{ syncSub }}</small></span>
        </button>
        <div v-if="isWeb && store.isOwner && store.branches" class="branch-switch">
          <label>Branch</label>
          <select class="select" :value="store.user && store.user.branch" @change="switchBranch($event.target.value)">
            <option v-for="(name, code) in store.branches" :key="code" :value="code">{{ name }} ({{ code }})</option>
          </select>
        </div>
        <div class="side-row">
          <button class="side-btn" @click="toggleTheme" :title="store.theme === 'dark' ? 'Light mode' : 'Dark mode'"><Icon :name="store.theme === 'dark' ? 'sun' : 'moon'" size="sm"/><span>{{ store.theme === 'dark' ? 'Light' : 'Dark' }}</span></button>
          <button class="side-btn" @click="signOut" title="Sign out (switch cashier)"><Icon name="user" size="sm"/><span>Sign out</span></button>
          <button v-if="!isWeb" class="side-btn" @click="requestQuit" title="Quit (Ctrl+Q)"><Icon name="power" size="sm"/><span>Quit</span></button>
        </div>
        <div class="db-status"><div><span class="dot"></span>Database: Connected</div><div class="muted">{{ store.status }}</div><div class="muted">v2.0 · Rental Billing System</div></div>
      </div>
    </aside>
    <main class="main">
      <header class="topbar">
        <button class="btn ghost icon-only menu-btn" @click="store.navOpen = true" aria-label="Menu"><Icon name="menu"/></button>
        <div><h1>{{ current.title }}</h1><div class="subtitle">{{ current.sub }}</div></div>
        <span class="spacer"></span>
        <button class="btn" @click="manualRefresh" title="Refresh all data (F5)"><Icon name="refresh" size="sm"/>Refresh Data<kbd>F5</kbd></button>
      </header>
      <div v-show="store.tab === 'billing'" class="page" style="padding-bottom:16px"><BillingPage :active="store.tab === 'billing'"/></div>
      <PendingReturnsPage v-if="visited.pending_returns" v-show="store.tab === 'pending_returns'" :active="store.tab === 'pending_returns'"/>
      <PendingPaymentsPage v-if="visited.pending" v-show="store.tab === 'pending'" :active="store.tab === 'pending'"/>
      <DailyPage v-if="visited.daily" v-show="store.tab === 'daily'" :active="store.tab === 'daily'"/>
      <CustomerReportPage v-if="visited.customer_report" v-show="store.tab === 'customer_report'" :active="store.tab === 'customer_report'"/>
      <AnalyticsPage v-if="visited.analytics" v-show="store.tab === 'analytics'" :active="store.tab === 'analytics'"/>
      <CustomersPage v-if="visited.customers" v-show="store.tab === 'customers'" :active="store.tab === 'customers'"/>
      <EquipmentPage v-if="store.isOwner && visited.equipment" v-show="store.tab === 'equipment'" :active="store.tab === 'equipment'"/>
      <TeamPage v-if="store.isOwner && visited.team" v-show="store.tab === 'team'" :active="store.tab === 'team'"/>
    </main>
  </div>`,
};

// ------------------------------------------------------------------ cloud sync status
const sync = reactive({ online: false, pending: 0, last_sync: null, error: null, running: false, data_rev: 0 });
let seenRev = null;
async function pollSync() {
  try {
    const st = await api("sync_status");
    Object.assign(sync, st);
    if (seenRev !== null && st.data_rev !== seenRev && store.phase === "app") reloadAll(); // changes arrived from the phone/web
    seenRev = st.data_rev;
  } catch (e) { /* ignore */ }
}
setInterval(pollSync, 4000);
if (IS_WEB) setInterval(() => { if (store.phase === "app") api("sync_now").catch(() => {}); }, 60000);
async function signOut() {
  const ok = await confirmBox("Sign out", "Sign out so another cashier can sign in?", { okText: "Sign out", cancelText: "Cancel" });
  if (!ok) return;
  await api("logout").catch(() => {});
  store.user = null; store.isOwner = false; store.tab = "billing"; store.phase = "login";
}

// ------------------------------------------------------------------ app-wide actions
function manualRefresh() { reloadAll(); }
async function quickBackup() {   // Ctrl+B: sync to the cloud now
  if ((await run("sync_now")) !== FAIL) toast("info", "Syncing", "Uploading changes to the cloud…", 3000);
}
let quitOpen = false;
async function requestQuit() {
  if (quitOpen) return;
  quitOpen = true;
  try {
    const ok = await confirmBox("Quit", "Do you want to quit the application?", { okText: "Quit", cancelText: "Cancel" });
    if (ok) await api("quit").catch(() => {});
  } finally { quitOpen = false; }
}
window.__requestQuit = () => { if (store.phase === "app") requestQuit(); else api("quit").catch(() => {}); };

window.addEventListener("keydown", (e) => {
  const k = e.key.toLowerCase();
  // never let the embedded browser reload the page or open its own dialogs
  if (e.key === "F5" || (e.ctrlKey && (k === "r" || k === "p" || k === "s" || k === "n" || k === "f" || k === "g" || k === "u" || k === "o" || k === "j"))) e.preventDefault();
  if (e.altKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) e.preventDefault();
  if (store.phase !== "app" || dialogs.length) return;
  if (e.key === "F5") { manualRefresh(); return; }
  if (!e.ctrlKey || e.altKey) return;
  if (k === "q") requestQuit();
  else if (k === "b") quickBackup();
  else if (window.BillingActions) {
    if (k === "n") window.BillingActions.clear();
    else if (k === "s") window.BillingActions.submit();
    else if (k === "p") window.BillingActions.print();
  }
});
document.addEventListener("contextmenu", (e) => { if (!(e.target.closest && e.target.closest("input, textarea"))) e.preventDefault(); });

// Background messages and the status bar counter (every 10 s, like main.py)
setInterval(async () => {
  try { for (const n of await api("notes")) toast(n.kind, n.title, n.message); } catch (e) { /* ignore */ }
}, 1500);
setInterval(() => { if (store.phase === "app") refreshStatus(); }, 10000);

// ------------------------------------------------------------------ root
createApp({
  components: { LoginView, Shell, DialogHost, ToastHost, Icon },
  setup() { return { store, closeApp: () => window.__requestQuit() }; },
  template: `
    <LoginView v-if="store.phase === 'login'"/>
    <div v-else-if="store.phase === 'booting'" class="boot">Opening database…</div>
    <div v-else-if="store.phase === 'fatal'" class="login">
      <div class="login-card">
        <div class="modal-icon error" style="margin-bottom:14px"><Icon name="alert" size="lg"/></div>
        <h1 style="font-size:18px">Database Error</h1>
        <p class="lead" style="white-space:pre-line;margin-top:8px">{{ store.fatal }}</p>
        <button class="btn primary" @click="closeApp">Close</button>
      </div>
    </div>
    <Shell v-else/>
    <div v-if="store.busy" class="loading-bar"></div>
    <DialogHost/>
    <ToastHost/>`,
}).mount("#app");

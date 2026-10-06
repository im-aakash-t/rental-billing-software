// pages.js - the report / directory pages (one per old Tkinter tab).
"use strict";

// Small helper: loads a list from the API, ignoring out-of-order responses.
function useLoader(fetcher) {
  const loading = ref(false);
  let seq = 0;
  async function load() {
    const my = ++seq;
    loading.value = true;
    try {
      const data = await fetcher();
      if (my === seq) return { data };
    } catch (e) {
      if (my === seq) await alertBox(e.kind || "error", e.title || "Error", e.message);
    } finally {
      if (my === seq) loading.value = false;
    }
    return null;
  }
  return { loading, load };
}
const starName = { template: '<span>{{ stripStar(value) }}<span v-if="hasStar(value)" class="star"> ★</span></span>', props: ["value"], methods: { stripStar, hasStar } };

// ======================================================================== Pending Returns (partial_returns_tab.py)
const PendingReturnsPage = {
  components: { Icon, Seg, Search, starName },
  props: { active: Boolean },
  setup(props) {
    const search = ref(""), sort = ref("new_to_old");
    const records = ref([]);
    const { loading, load: fetch } = useLoader(() => api("pending_returns", { search: search.value, sort: sort.value }));
    const load = async () => { const r = await fetch(); if (r) records.value = r.data; };
    watch(search, debounce(load, 200));
    watch(sort, load);
    useReload(props, load);
    async function processReturn(rec) {
      const id = await run("rental_id_for_bill", { bill_no: rec.bill_no });
      if (id === FAIL || !id) return;
      store.tab = "billing";
      bus.emit("return:load", id);
    }
    const printList = () => run("print_pending_returns", { records: records.value });
    const totalItems = (rec) => rec.items.reduce((a, i) => a + (parseInt(i.taken, 10) || 0), 0);
    return { search, sort, records, loading, load, processReturn, printList, totalItems };
  },
  template: `
  <div class="page fill">
    <div class="toolbar">
      <Search v-model="search" placeholder="Search bill, name, phone, address or item" width="340px"/>
      <span class="tb-label" style="margin-left:6px">Date</span>
      <Seg v-model="sort" :options="[{value:'new_to_old',label:'New to Old'},{value:'old_to_new',label:'Old to New'}]"/>
      <span class="grow"></span>
      <button class="btn" @click="load"><Icon name="refresh" size="sm"/>Refresh List</button>
      <button class="btn" @click="printList"><Icon name="printer" size="sm"/>Print List</button>
    </div>
    <div class="t-muted" style="font-size:12.5px;margin-top:-4px">{{ records.length }} customers with items still out. Double-click a bill, or use <b>Process Return</b>, to open it in Return Processing.</div>
    <div class="pr-list" style="overflow:auto;min-height:0;flex:1;padding-bottom:4px">
      <div v-for="rec in records" :key="rec.bill_no" class="pr-card" @dblclick="processReturn(rec)">
        <div><div class="pr-bill">{{ rec.bill_no }}</div><div class="pr-date num">{{ rec.date }}</div></div>
        <div><div class="pr-name"><starName :value="rec.name"/></div><div class="pr-sub num">{{ rec.phone }}</div></div>
        <div class="pr-addr">{{ rec.address || '—' }}</div>
        <div class="pr-items"><span v-for="(it, i) in rec.items" :key="i" class="chip">{{ it.name }} <b>× {{ it.taken }}</b></span></div>
        <button class="btn sm primary" @click="processReturn(rec)"><Icon name="undo" size="sm"/>Process Return</button>
      </div>
      <div v-if="!records.length && !loading" class="empty card"><Icon name="check"/><div>No pending returns.</div></div>
    </div>
  </div>`,
};

// ======================================================================== Pending / Refunds (pending_tab.py)
const PendingPaymentsPage = {
  components: { Icon, Seg, Search, DataTable, starName },
  props: { active: Boolean },
  setup(props) {
    const st = reactive({ search: "", filter: "all", return_status: "all", sort: "new_to_old" });
    const rows = ref([]);
    const { loading, load: fetch } = useLoader(() => api("pending_payments", Object.assign({}, st)));
    const load = async () => { const r = await fetch(); if (r) rows.value = r.data; };
    watch(() => st.search, debounce(load, 200));
    watch(() => [st.filter, st.return_status, st.sort], load);
    useReload(props, load);
    const printList = () => run("print_pending_payments", { rows: rows.value.map((r) => r.values), filter_type: st.filter });
    const sumBal = computed(() => {
      let collect = 0, refund = 0;
      for (const r of rows.value) { const b = L.safeFloat(r.values[7]); if (b > 0) collect += b; else refund += -b; }
      return { collect: "₹" + L.fmtComma2(collect), refund: "₹" + L.fmtComma2(refund) };
    });
    const columns = [
      { idx: 0, label: "Bill No", width: "96px", cls: () => "strong num" },
      { idx: 1, label: "Name" },
      { idx: 2, label: "Phone", width: "120px", cls: () => "num" },
      { idx: 3, label: "Date", width: "96px", cls: () => "num" },
      { idx: 4, label: "Due", width: "110px", align: "r", cls: () => "num" },
      { idx: 5, label: "Advance", width: "110px", align: "r", cls: () => "num" },
      { idx: 6, label: "Paid", width: "110px", align: "r", cls: () => "num" },
      { idx: 7, label: "Balance", width: "120px", align: "r", cls: (r) => "num t-strong " + (r.tag === "debt" ? "t-red" : "t-green") },
    ];
    return { st, rows, loading, load, printList, columns, sumBal };
  },
  template: `
  <div class="page fill">
    <div class="toolbar">
      <Search v-model="st.search" placeholder="Search name or phone" width="260px"/>
      <span class="tb-label">Filter</span>
      <Seg v-model="st.filter" :options="[{value:'all',label:'All'},{value:'collect',label:'To Collect (Debt)',dot:'var(--danger)'},{value:'refund',label:'To Refund',dot:'var(--success)'}]"/>
      <span class="tb-label">Status</span>
      <Seg v-model="st.return_status" :options="[{value:'all',label:'All'},{value:'returned',label:'Returned'},{value:'not_returned',label:'Not Returned'}]"/>
      <span class="tb-label">Date</span>
      <Seg v-model="st.sort" :options="[{value:'new_to_old',label:'New to Old'},{value:'old_to_new',label:'Old to New'}]"/>
      <span class="grow"></span>
      <button class="btn" @click="printList"><Icon name="printer" size="sm"/>Print List</button>
    </div>
    <div class="card flush" style="display:flex;flex-direction:column;flex:1;min-height:0">
      <DataTable :columns="columns" :rows="rows" empty-text="Nothing pending for these filters." empty-icon="check">
        <template #cell-1="{ value }"><starName :value="value"/></template>
      </DataTable>
      <div class="table-foot"><span>{{ rows.length }} bills</span><span v-if="loading">· Loading…</span>
        <span style="margin-left:auto">To collect <b class="t-red num">{{ sumBal.collect }}</b> &nbsp;·&nbsp; To refund <b class="t-green num">{{ sumBal.refund }}</b></span></div>
    </div>
  </div>`,
};

// ======================================================================== Day's Overview (daily_report_tab.py)
const DailyPage = {
  components: { Icon, Search, DatePicker, DataTable, Stat },
  props: { active: Boolean },
  setup(props) {
    const st = reactive({ from_date: todayStr(), to_date: todayStr(), search: "" });
    const rows = ref([]);
    const cards = reactive({ rented: "0", returned: "0", cash_in: "0", cash_out: "0", gpay_in: "0", gpay_out: "0" });
    let totals = { rented: 0, returned: 0, cash_in: 0, cash_out: 0, gpay_in: 0, gpay_out: 0 };
    const { loading, load: fetch } = useLoader(() => api("daily_overview", Object.assign({}, st)));
    const load = async () => {
      const r = await fetch();
      if (!r) return;
      rows.value = r.data.rows;
      if (r.data.ok) { Object.assign(cards, r.data.cards); totals = r.data.totals; }
    };
    watch(() => st.search, debounce(load, 200));
    watch(() => [st.from_date, st.to_date], load);
    useReload(props, load);
    const printLedger = () => run("print_daily", { rows: rows.value.map((r) => r.values), from_date: st.from_date, to_date: st.to_date, totals });
    const columns = [
      { idx: 0, label: "Date & Time", width: "150px", cls: () => "num" },
      { idx: 1, label: "Bill No", width: "90px", cls: () => "strong num" },
      { idx: 2, label: "Customer Name", width: "18%" },
      { idx: 3, label: "Type", width: "150px" },
      { idx: 4, label: "Details" },
      { idx: 5, label: "Amount (₹)", width: "120px", align: "r", cls: (r) => "num t-strong " + (r.tag === "in" ? "t-green" : r.tag === "out" ? "t-red" : "t-muted") },
      { idx: 6, label: "Mode", width: "80px", align: "c" },
    ];
    const typePill = (r) => r.tag === "in" ? "green" : r.tag === "out" ? "red" : (r.values[3] === "Returned Items" ? "blue" : "amber");
    return { st, rows, cards, loading, printLedger, columns, typePill };
  },
  template: `
  <div class="page fill">
    <div class="toolbar">
      <span class="tb-label">From</span><DatePicker v-model="st.from_date"/>
      <span class="tb-label">To</span><DatePicker v-model="st.to_date"/>
      <Search v-model="st.search" placeholder="Search bill or customer" width="260px"/>
      <span class="grow"></span>
      <button class="btn" @click="printLedger"><Icon name="printer" size="sm"/>Print Ledger</button>
    </div>
    <div class="stat-grid" style="grid-template-columns:repeat(6,minmax(0,1fr))">
      <Stat label="Rented Items" :value="cards.rented" icon="package" tone="amber"/>
      <Stat label="Returned Items" :value="cards.returned" icon="undo" tone="blue"/>
      <Stat label="Cash In (+)" :value="cards.cash_in" icon="cash" tone="green" small/>
      <Stat label="Cash Out (−)" :value="cards.cash_out" icon="cash" tone="red" small/>
      <Stat label="GPay In (+)" :value="cards.gpay_in" icon="phone" tone="green" small/>
      <Stat label="GPay Out (−)" :value="cards.gpay_out" icon="phone" tone="red" small/>
    </div>
    <div class="card flush" style="display:flex;flex-direction:column;flex:1;min-height:0">
      <DataTable :columns="columns" :rows="rows" empty-text="No transactions in this date range." empty-icon="calendar">
        <template #cell-3="{ row, value }"><span class="pill" :class="typePill(row)">{{ value }}</span></template>
      </DataTable>
      <div class="table-foot"><span>{{ rows.length }} entries</span><span v-if="loading">· Loading…</span></div>
    </div>
  </div>`,
};

// ======================================================================== Customer Report (customer_report_tab.py)
const CustomerReportPage = {
  components: { Icon, Search, DataTable, starName },
  props: { active: Boolean },
  setup(props) {
    const search = ref("");
    const rows = ref([]);
    const summary = reactive({ text: "Enter a name or phone number to view report.", kind: "muted", totals: null });
    const { loading, load: fetch } = useLoader(() => api("customer_report", { search: search.value }));
    const load = async () => {
      const r = await fetch();
      if (!r) return;
      rows.value = r.data.rows;
      summary.text = r.data.summary; summary.kind = r.data.summary_kind; summary.totals = r.data.totals || null;
    };
    watch(search, debounce(load, 200));
    useReload(props, load);
    const printList = () => run("print_customer_report", { rows: rows.value.map((r) => r.values) });
    const money = (v) => "₹" + L.fmtComma2(v);
    const columns = [
      { idx: 0, label: "Bill No", width: "86px", cls: () => "strong num" },
      { idx: 1, label: "Name", width: "13%" },
      { idx: 2, label: "Phone", width: "108px", cls: () => "num" },
      { idx: 3, label: "Date", width: "82px", cls: () => "num" },
      { idx: 4, label: "Machines" },
      { idx: 5, label: "Total", width: "90px", align: "r", cls: () => "num" },
      { idx: 6, label: "Advance", width: "90px", align: "r", cls: () => "num" },
      { idx: 7, label: "Adv Mode", width: "76px", align: "c" },
      { idx: 8, label: "Return Date", width: "92px", align: "c", cls: () => "num" },
      { idx: 9, label: "Paid", width: "86px", align: "r", cls: () => "num" },
      { idx: 10, label: "Refund", width: "86px", align: "r", cls: () => "num" },
      { idx: 11, label: "Paid Mode", width: "80px", align: "c" },
      { idx: 12, label: "Balance", width: "96px", align: "r", cls: (r) => "num t-strong " + (r.tag === "positive" ? "t-red" : r.tag === "negative" ? "t-green" : "") },
    ];
    return { search, rows, summary, loading, load, printList, columns, money };
  },
  template: `
  <div class="page fill">
    <div class="toolbar">
      <Search v-model="search" placeholder="Search by name or phone" width="320px"/>
      <button class="btn" @click="load"><Icon name="refresh" size="sm"/>Refresh</button>
      <span class="grow"></span>
      <button class="btn" @click="printList"><Icon name="printer" size="sm"/>Print List</button>
    </div>
    <div v-if="summary.totals" class="stat-grid" style="grid-template-columns:repeat(4,minmax(0,1fr))">
      <Stat label="Total Billed" :value="money(summary.totals.billed)" icon="receipt" tone="indigo" small/>
      <Stat label="Total Paid" :value="money(summary.totals.paid)" icon="wallet" tone="green" small/>
      <Stat label="Total Refund" :value="money(summary.totals.refund)" icon="arrowOut" tone="purple" small/>
      <Stat label="Net Balance" :value="money(summary.totals.balance)" icon="trend" :tone="summary.totals.balance > 0 ? 'red' : 'green'" small/>
    </div>
    <div v-else class="card" style="padding:12px 16px" :class="summary.kind === 'error' ? 't-red' : 't-muted'">{{ summary.text }}</div>
    <div class="card flush" style="display:flex;flex-direction:column;flex:1;min-height:0">
      <DataTable :columns="columns" :rows="rows" :empty-text="search.trim() ? 'No bills found for this customer.' : 'Search for a customer to see their history.'" empty-icon="usersearch">
        <template #cell-1="{ value }"><starName :value="value"/></template>
        <template #cell-8="{ value }"><span v-if="value === 'Open'" class="pill amber">Open</span><span v-else>{{ value }}</span></template>
      </DataTable>
      <div class="table-foot"><span>{{ rows.length }} bills</span><span v-if="loading">· Loading…</span></div>
    </div>
  </div>`,
};

// ======================================================================== Analytics (analytics_dashboard.py)
const AnalyticsPage = {
  components: { Icon, Seg, Search, DatePicker, DataTable, Stat },
  props: { active: Boolean },
  setup(props) {
    const sub = ref("overview");
    // Overview: KPI cards
    const kpi = reactive({ pay_filter: "All", profit_date: todayStr(), data: { pending_quantity: "0", pending_payments: "₹0.00", refund_to_be_done: "₹0.00", profit: "₹0.00" } });
    const updateKpis = async () => { try { kpi.data = await api("analytics_kpis", { pay_filter: kpi.pay_filter, profit_date: kpi.profit_date }); } catch (e) { await alertBox("error", e.title, e.message); } };
    watch(() => [kpi.pay_filter, kpi.profit_date], updateKpis);
    // Transaction splits
    const splits = reactive({ from_date: todayStr(), to_date: todayStr(), data: { gpay_in: "₹0.00", gpay_out: "₹0.00", cash_in: "₹0.00", cash_out: "₹0.00" } });
    const updateSplits = async () => { try { splits.data = await api("analytics_splits", { from_date: splits.from_date, to_date: splits.to_date }); } catch (e) { await alertBox("error", e.title, e.message); } };
    watch(() => [splits.from_date, splits.to_date], updateSplits);
    // Delete old data
    const del = reactive({ from: todayStr(), to: todayStr() });
    async function doDelete() {
      const ok = await confirmBox("Confirm Deletion", `Are you absolutely sure you want to delete transactions from ${del.from} to ${del.to}?\n\nThis cannot be undone!`, { kind: "danger", okText: "Delete Records", cancelText: "Cancel" });
      if (!ok) return;
      const r = await run("delete_old_data", { start_str: del.from, end_str: del.to });
      if (r === FAIL) return;
      await alertBox(r.deleted ? "success" : "info", r.deleted ? "Success" : "Result", r.message);
      if (r.deleted) reloadAll();
    }
    // Stock status
    const stock = reactive({ search: "", rows: [] });
    const loadStock = async () => { try { stock.rows = await api("analytics_stock", { search: stock.search }); } catch (e) { await alertBox("error", e.title, e.message); } };
    watch(() => stock.search, debounce(loadStock, 150));
    const printStock = () => run("print_stock", { rows: stock.rows.map((r) => r.values) });
    const stockCols = [
      { idx: 0, label: "Machine Name" },
      { idx: 1, label: "Total Stock", width: "140px", align: "c", cls: () => "num" },
      { idx: 2, label: "Currently Rented", width: "160px", align: "c", cls: () => "num" },
      { idx: 3, label: "Available Now", width: "150px", align: "c", cls: (r) => "num t-strong " + (r.tag === "out_of_stock" ? "t-red" : "t-green") },
    ];
    // Top customers
    const top = reactive({ from_date: todayStr(), to_date: todayStr(), limit: "15", title: "🏆 Top 15 Customers", rows: [] });
    const loadTop = async () => {
      try { const r = await api("analytics_top_customers", { from_date: top.from_date, to_date: top.to_date, limit: top.limit }); top.rows = r.rows; top.title = r.title; }
      catch (e) { await alertBox("error", e.title, e.message); }
    };
    watch(() => [top.from_date, top.to_date], loadTop);
    const topCols = [
      { idx: 0, label: "Rank", width: "80px", align: "c" },
      { idx: 1, label: "Name" },
      { idx: 2, label: "Phone", width: "160px", cls: () => "num" },
      { idx: 3, label: "Rentals", width: "120px", align: "c", cls: () => "num" },
      { idx: 4, label: "Total Spent", width: "160px", align: "r", cls: () => "num t-strong" },
    ];
    const reloadAllAnalytics = async () => { await Promise.all([updateKpis(), updateSplits(), loadStock(), loadTop()]); };
    useReload(props, reloadAllAnalytics);
    return { sub, kpi, splits, del, doDelete, stock, printStock, stockCols, top, loadTop, topCols };
  },
  template: `
  <div class="page">
    <div class="subtabs">
      <button :class="{ on: sub === 'overview' }" @click="sub = 'overview'"><Icon name="chart" size="sm"/>Overview</button>
      <button :class="{ on: sub === 'stock' }" @click="sub = 'stock'"><Icon name="package" size="sm"/>Stock Status</button>
      <button :class="{ on: sub === 'top' }" @click="sub = 'top'"><Icon name="trophy" size="sm"/>Top Customers</button>
    </div>

    <div v-show="sub === 'overview'" style="display:flex;flex-direction:column;gap:16px">
      <div class="stat-grid" style="grid-template-columns:repeat(4,minmax(0,1fr))">
        <Stat label="Pending Quantity" :value="kpi.data.pending_quantity" icon="package" tone="amber"/>
        <Stat label="Pending Payments" :value="kpi.data.pending_payments" icon="wallet" tone="red">
          <template #extra><select class="select" style="height:26px;font-size:12px;width:124px" v-model="kpi.pay_filter">
            <option>All</option><option>Returned</option><option>Not Returned</option></select></template>
        </Stat>
        <Stat label="Refund to be Done" :value="kpi.data.refund_to_be_done" icon="arrowOut" tone="purple"/>
        <Stat label="Profit on Date" :value="kpi.data.profit" icon="trend" tone="green">
          <template #extra><DatePicker v-model="kpi.profit_date" small/></template>
        </Stat>
      </div>

      <div class="card">
        <div class="card-head"><h3><Icon name="layers"/>Transaction Splits</h3><span class="spacer"></span>
          <span class="tb-label">From</span><DatePicker v-model="splits.from_date" small/>
          <span class="tb-label">To</span><DatePicker v-model="splits.to_date" small/>
        </div>
        <div class="card-body">
          <div class="stat-grid" style="grid-template-columns:repeat(4,minmax(0,1fr))">
            <Stat label="Received GPay" :value="splits.data.gpay_in" icon="arrowIn" tone="green" small/>
            <Stat label="Refunded GPay" :value="splits.data.gpay_out" icon="arrowOut" tone="red" small/>
            <Stat label="Received Cash" :value="splits.data.cash_in" icon="arrowIn" tone="green" small/>
            <Stat label="Refunded Cash" :value="splits.data.cash_out" icon="arrowOut" tone="red" small/>
          </div>
        </div>
      </div>

      <div class="card danger-zone">
        <div class="card-head"><h3><Icon name="trash"/>Delete Old Data (Keeps Customers)</h3></div>
        <div class="card-body" style="display:flex;flex-direction:column;gap:12px">
          <div class="warn-text">WARNING: This will permanently wipe financial and item records for the selected date range.<br>Customer info (Name, Phone, Address) will be retained for auto-complete.</div>
          <div class="toolbar">
            <span class="tb-label">From</span><DatePicker v-model="del.from"/>
            <span class="tb-label">To</span><DatePicker v-model="del.to"/>
            <button class="btn danger-solid" @click="doDelete"><Icon name="trash" size="sm"/>Delete Records</button>
          </div>
        </div>
      </div>
    </div>

    <div v-show="sub === 'stock'" class="card flush" style="display:flex;flex-direction:column;height:calc(100% - 58px);min-height:360px">
      <div class="card-head"><h3><Icon name="package"/>Live Stock Status</h3><span class="t-muted" style="font-size:12px">Cross-referenced with active rentals</span>
        <span class="spacer"></span><Search v-model="stock.search" placeholder="Search machine" width="220px"/>
        <button class="btn" @click="printStock"><Icon name="printer" size="sm"/>Print Stock</button></div>
      <DataTable :columns="stockCols" :rows="stock.rows" empty-text="No machines found." empty-icon="package"/>
    </div>

    <div v-show="sub === 'top'" class="card flush" style="display:flex;flex-direction:column;height:calc(100% - 58px);min-height:360px">
      <div class="card-head" style="flex-wrap:wrap"><h3><Icon name="trophy"/>{{ top.title.replace('🏆 ', '') }}</h3><span class="spacer"></span>
        <span class="tb-label">From</span><DatePicker v-model="top.from_date" small/>
        <span class="tb-label">To</span><DatePicker v-model="top.to_date" small/>
        <span class="tb-label">Top N</span><input class="input num" style="width:70px;height:28px" v-model="top.limit" @keydown.enter="loadTop">
        <button class="btn sm" @click="loadTop"><Icon name="refresh" size="sm"/>Update</button></div>
      <DataTable :columns="topCols" :rows="top.rows.map(v => ({ values: v }))" empty-text="No customers in this date range." empty-icon="trophy">
        <template #cell-0="{ value }"><span class="pill" :class="value === '1' ? 'amber' : (value === '2' || value === '3' ? 'blue' : 'gray')">#{{ value }}</span></template>
      </DataTable>
    </div>
  </div>`,
};

// ======================================================================== Customers (customers_tab.py)
const CustomersPage = {
  components: { Icon, Search, DataTable, starName },
  props: { active: Boolean },
  setup(props) {
    const st = reactive({ search: "", filter: "All Customers" });
    const rows = ref([]);
    const selected = ref(null);
    const { loading, load: fetch } = useLoader(() => api("customers", Object.assign({}, st)));
    const load = async () => {
      const r = await fetch();
      if (!r) return;
      rows.value = r.data;
      if (selected.value !== null && !r.data.some((c) => c.id === selected.value)) selected.value = null;
    };
    watch(() => st.search, debounce(load, 200));
    watch(() => st.filter, load);
    useReload(props, load);

    async function openEditor(c) {
      const editing = !!c;
      await formBox({
        title: editing ? "Edit Customer" : "Add New Customer", icon: "user", okText: "Save Customer", wide: true,
        fields: [
          { key: "name", label: "Name", required: true, value: editing ? c.raw_name : "", autofocus: true },
          { key: "phone", label: "Primary Phone", required: true, value: editing ? c.phone : "", disabled: editing },
          { key: "phone2", label: "Secondary Phone", value: editing ? c.phone2 : "" },
          { key: "address", label: "Address", type: "textarea", value: editing ? c.address : "" },
          { key: "is_regular", label: "⭐ Mark as Regular Customer", type: "checkbox", value: editing ? c.is_regular : false },
        ],
        validate: (v) => (!v.name.trim() || !v.phone.trim()) ? "Name and Primary Phone are required!" : null,
        onSubmit: async (v) => {
          const r = await run("save_customer", { customer_id: editing ? c.id : null, name: v.name, phone: v.phone, phone2: v.phone2, address: v.address, is_regular: v.is_regular });
          if (r === FAIL) return false;
          reloadAll();
          return true;
        },
      });
    }
    const editSelected = () => { const c = rows.value.find((x) => x.id === selected.value); if (c) openEditor(c); };
    const printList = () => run("print_customers", { rows: rows.value.map((c) => [c.name, c.phone, c.phone2, c.address, c.regular]) });
    const columns = [
      { key: "name", label: "Customer Name", width: "22%" },
      { key: "phone", label: "Primary Phone", width: "140px", cls: () => "num" },
      { key: "phone2", label: "Secondary Phone", width: "140px", cls: () => "num" },
      { key: "address", label: "Address" },
      { key: "regular", label: "Regular?", width: "110px", align: "c" },
    ];
    return { st, rows, selected, loading, openEditor, editSelected, printList, columns };
  },
  template: `
  <div class="page fill">
    <div class="toolbar">
      <Search v-model="st.search" placeholder="Search name or phone" width="280px"/>
      <select class="select" style="width:170px" v-model="st.filter"><option>All Customers</option><option>Regular Only</option><option>Non-Regular Only</option></select>
      <span class="grow"></span>
      <button class="btn primary" @click="openEditor(null)"><Icon name="plus" size="sm"/>Add New Customer</button>
      <button class="btn" :disabled="selected === null" @click="editSelected"><Icon name="edit" size="sm"/>Edit Selected</button>
      <button class="btn" @click="printList"><Icon name="printer" size="sm"/>Print List</button>
    </div>
    <div class="card flush" style="display:flex;flex-direction:column;flex:1;min-height:0">
      <DataTable :columns="columns" :rows="rows" :row-key="c => c.id" :selected-key="selected" selectable
                 @select="c => selected = c.id" @activate="openEditor" empty-text="No customers found." empty-icon="users">
        <template #cell-name="{ value }"><starName :value="value"/></template>
        <template #cell-regular="{ row }"><span v-if="row.is_regular" class="pill amber">★ Regular</span><span v-else class="t-muted">No</span></template>
      </DataTable>
      <div class="table-foot"><span>{{ rows.length }} customers</span><span v-if="loading">· Loading…</span><span style="margin-left:auto">Double-click a customer to edit</span></div>
    </div>
  </div>`,
};

// ======================================================================== Equipment Analytics (materials_report_tab.py, owner only)
const EquipmentPage = {
  components: { Icon, Search, DatePicker, DataTable, Stat },
  props: { active: Boolean },
  setup(props) {
    const st = reactive({ from_date: daysAgoStr(60), to_date: todayStr(), search: "" });
    const rows = ref([]);
    const sum = reactive({ total_revenue: "₹0.00", top_earner: "-", top_freq: "-" });
    const { loading, load: fetch } = useLoader(() => api("equipment_analytics", Object.assign({}, st)));
    const load = async () => {
      const r = await fetch();
      if (!r) return;
      rows.value = r.data.rows;
      if (r.data.ok) { sum.total_revenue = r.data.total_revenue; sum.top_earner = r.data.top_earner; sum.top_freq = r.data.top_freq; }
    };
    watch(() => st.search, debounce(load, 200));
    watch(() => [st.from_date, st.to_date], load);
    useReload(props, load);
    async function exportCsv() {
      const r = await run("export_equipment_csv", { rows: rows.value.map((x) => x.values) });
      if (r && r !== FAIL) await alertBox("success", "Success", r.message);
    }
    const printReport = () => run("print_equipment", { rows: rows.value.map((x) => x.values), from_date: st.from_date, to_date: st.to_date,
      total_revenue: sum.total_revenue, top_earner: sum.top_earner, top_freq: sum.top_freq });
    const columns = [
      { idx: 0, label: "Equipment Type" },
      { idx: 1, label: "Frequency (No. of Bills)", width: "190px", align: "c", cls: () => "num" },
      { idx: 2, label: "Total Revenue (₹)", width: "170px", align: "r", cls: () => "num t-strong" },
      { idx: 3, label: "Contribution (%)", width: "150px", align: "c", cls: () => "num" },
      { idx: 4, label: "Revenue Weight", width: "22%", title: false },
    ];
    return { st, rows, sum, loading, exportCsv, printReport, columns };
  },
  template: `
  <div class="page fill">
    <div class="toolbar">
      <span class="tb-label">From</span><DatePicker v-model="st.from_date"/>
      <span class="tb-label">To</span><DatePicker v-model="st.to_date"/>
      <Search v-model="st.search" placeholder="Search equipment" width="240px"/>
      <span class="grow"></span>
      <button class="btn" @click="exportCsv"><Icon name="download" size="sm"/>Export CSV</button>
      <button class="btn" @click="printReport"><Icon name="printer" size="sm"/>Print Report</button>
    </div>
    <div class="stat-grid" style="grid-template-columns:repeat(3,minmax(0,1fr))">
      <Stat label="Total Revenue" :value="sum.total_revenue" icon="wallet" tone="green"/>
      <Stat label="Top Earning Equipment" :value="sum.top_earner" icon="flame" tone="indigo" small/>
      <Stat label="Most Frequent on Bills" :value="sum.top_freq" icon="trend" tone="red" small/>
    </div>
    <div class="t-muted" style="font-size:12.5px;margin-top:-4px">Only completed bills (all items returned and balance settled) whose rental and return dates both fall in the range are counted.</div>
    <div class="card flush" style="display:flex;flex-direction:column;flex:1;min-height:0">
      <DataTable :columns="columns" :rows="rows" empty-text="No completed bills in this date range." empty-icon="wrench">
        <template #cell-4="{ row }"><div class="bar"><span :style="{ width: (row.weight * 100).toFixed(1) + '%' }"></span></div></template>
      </DataTable>
      <div class="table-foot"><span>{{ rows.length }} equipment types</span><span v-if="loading">· Loading…</span></div>
    </div>
  </div>`,
};

window.Pages = { PendingReturnsPage, PendingPaymentsPage, DailyPage, CustomerReportPage, AnalyticsPage, CustomersPage, EquipmentPage };

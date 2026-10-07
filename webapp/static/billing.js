// billing.js - Outward Billing page and the Return Processing panel.
// Behaviour mirrors form_tab.py / form_logic.py / return_form.py.
"use strict";

const MAX_MACHINES = 5;

function askCashier(title, actionName) {
  return formBox({
    title, icon: "user", okText: actionName,
    fields: [{ key: "cashier", label: "Cashier Name", required: true, autofocus: true }],
    validate: (v) => v.cashier.trim() ? null : "Cashier Name is required.",
  }).then((v) => (v ? v.cashier.trim() : null));
}

// ======================================================================== Return panel
const ReturnPanel = {
  components: { Icon, Seg, DatePicker },
  setup() {
    const blank = () => ({
      rental_id: "", date: todayStr(), time: nowTimeStr(), rental_days: "1", due: "0.00", deduction: "0.00",
      damage: "0.00", advance: "0.00", past_due: "0.00", refund: "0.00", amount_paid: "0.00", balance: "0.00",
      payment_mode: "Cash",
    });
    const f = reactive(blank());
    const info = reactive({ bill_no: "", name: "" });
    const dedDays = ref("");
    const steppers = reactive(Array.from({ length: 5 }, () => ({ label: "", max: 0, value: "0" })));
    const steppersEnabled = ref(false);   // the Tk steppers start disabled until a rental is loaded
    const frozen = ref(false);            // set_return_form_state('disabled') / calculation_frozen
    const balColor = ref("");
    const history = reactive({ Paid: [], Refund: [], Return: [] });
    const histMode = ref("Refund");
    let rents = [], startDate = null, startTime = null, rentedQty = [];
    let loading = true, updatingDeduction = false, loadSeq = 0;

    const dailyRent = () => L.pySum(rents.map((r) => L.safeFloat(r)));

    function netFor(o) {
      const [, net] = L.masterBalance({
        daily_rent: rents.length ? dailyRent() : 0.0,
        rental_days: L.safeInt(o.rental_days) || 1,
        advance_paid: o.advance, installments_paid: 0.0,
        damage_charges: o.damage, discount_deduction: o.deduction,
        final_amount_paid: o.amount_paid, refund_given: o.refund,
        is_returned: true, manual_due_override: o.due,
      });
      return net;
    }
    function recalcBalanceOnly() {
      const net = netFor(f);
      f.balance = L.fmt2(net);
      balColor.value = net !== 0 ? "red" : "green";
    }
    function recalcDue() {
      if (loading || !rents.length || frozen.value) return;
      const days = L.returnRentalDays(startDate, startTime, f.date, f.time);
      const [due] = L.masterBalance({ daily_rent: dailyRent(), rental_days: days, advance_paid: f.advance, is_returned: false });
      f.due = L.fmt2(due);
      f.rental_days = String(days);
      recalcBalanceOnly();
    }
    function setState(state) {
      frozen.value = state === "disabled";
      steppersEnabled.value = state !== "disabled";
      if (state !== "disabled" && !loading) recalcDue();
    }
    function checkFullyReturned() {
      let idx = 0, all = true;
      for (const qty of rentedQty) {
        const q = L.safeInt(qty);
        if (q > 0) {
          if (idx < 5) {
            if (L.safeInt(steppers[idx].value) < q) all = false;
            idx++;
          }
        }
      }
      return all;
    }
    function freezeCheck() {
      if (checkFullyReturned() && Math.abs(L.safeFloat(f.balance)) < 0.01) setState("disabled");
      else setState("normal");
    }
    function clearFields() {
      setState("normal");
      Object.assign(f, blank());
      dedDays.value = "";
      for (const s of steppers) { s.label = ""; s.max = 0; s.value = "0"; }
      history.Paid = []; history.Refund = []; history.Return = [];
      info.bill_no = ""; info.name = "";
      balColor.value = "";
    }

    // --- field events (the Tk traces / key bindings)
    const onDateTime = () => { if (!frozen.value) recalcDue(); };
    const onDamage = () => recalcBalanceOnly();
    function onDeductionField() {
      recalcBalanceOnly();
      if (updatingDeduction) return;
      const v = dedDays.value.trim();
      if (v) {
        const days = L.safeFloat(v);
        const daily = rents.length ? dailyRent() : 0.0;
        if (Math.abs(L.safeFloat(f.deduction) - days * daily) > 0.01) {
          updatingDeduction = true; dedDays.value = ""; updatingDeduction = false;
        }
      }
    }
    function onDeductionDays() {
      if (updatingDeduction) return;
      const v = dedDays.value.trim();
      if (v) {
        const days = L.safeFloat(v);
        const daily = rents.length ? dailyRent() : 0.0;
        updatingDeduction = true;
        f.deduction = L.fmt2(days * daily);
        onDeductionField();
        updatingDeduction = false;
      }
    }

    // --- steppers (CustomStepper)
    function validateStepper(s) {
      if (!steppersEnabled.value) return;
      if (!s.value) return;
      const n = L.pyInt(s.value);
      if (n === null) return;
      if (n > s.max) s.value = String(s.max);
      else if (n < 0) s.value = "0";
    }
    function stepVal(s) { const n = L.pyInt(s.value || "0"); return n === null ? 0 : n; }
    function inc(s) { if (!steppersEnabled.value) return; const v = stepVal(s); if (v < s.max) { s.value = String(v + 1); validateStepper(s); } }
    function dec(s) { if (!steppersEnabled.value) return; const v = stepVal(s); if (v > 0) { s.value = String(v - 1); validateStepper(s); } }

    // --- loading a rental (update_return_fields_from_selection)
    async function load(rentalId, preloaded) {
      const seq = ++loadSeq;
      loading = true;
      clearFields();
      let data = preloaded;
      if (data === undefined) {
        try { data = await api("return_load", { rental_id: rentalId }); } catch (e) { data = null; }
      }
      if (seq !== loadSeq) return;
      if (data) {
        rents = data.rents; startDate = data.start_date; startTime = data.start_time; rentedQty = data.rented_quantities;
        info.bill_no = data.bill_no; info.name = data.name;
        f.rental_id = data.rental_id;
        f.advance = data.advance;
        history.Paid = data.history.Paid; history.Refund = data.history.Refund; history.Return = data.history.Return;
        for (const k of ["date", "time", "rental_days", "due", "damage", "deduction", "amount_paid", "refund", "payment_mode"]) {
          if (k in data.fields) f[k] = data.fields[k];
        }
        recalcBalanceOnly(); // the amount/deduction/damage/refund write-traces
        f.past_due = data.past_due;
        data.steppers.forEach((s, i) => {
          steppers[i].label = s.label; steppers[i].max = s.max; steppers[i].value = s.value;
          validateStepper(steppers[i]);
        });
      } else {
        rents = []; rentedQty = [];
        loading = false;
        return; // could not load: leave the panel cleared and editable
      }
      loading = false;
      if (!frozen.value) recalcDue(); else recalcBalanceOnly();
      freezeCheck();
    }
    bus.on("return:load", (id, preloaded) => load(id, preloaded));

    const snapshot = () => ({
      date: f.date, time: f.time, rental_days: f.rental_days, due: f.due, deduction: f.deduction,
      damage: f.damage, balance: f.balance, amount_paid: f.amount_paid, refund: f.refund, payment_mode: f.payment_mode,
    });
    const stepperValues = () => steppers.map((s) => s.value);

    async function onSubmitClick() {
      const rentalId = f.rental_id;
      if (!rentalId) return;
      const cashier = await askCashier("Submit Return", "Submit Return");
      if (cashier === null) return;
      const r = await run("return_submit", { rental_id: rentalId, fields: snapshot(), steppers: stepperValues(), cashier_name: cashier });
      if (r === FAIL || !r) return;
      await alertBox("success", "Success", r.message);
      await load(rentalId);
      if (checkFullyReturned() && Math.abs(L.safeFloat(f.balance)) < 0.01) setState("disabled");
      reloadAll();
    }

    async function openMoney(kind) {
      if (!f.rental_id) { await alertBox("warning", "Error", "Please select a rental record first."); return; }
      const isRefund = kind === "refund";
      await formBox({
        title: isRefund ? "Add Refund" : "Add Installment Payment",
        icon: isRefund ? "arrowOut" : "wallet",
        okText: isRefund ? "Add Refund" : "Add Payment",
        fields: [
          { key: "amount", label: isRefund ? "Refund Amount (₹)" : "Payment Amount (₹)", numeric: true, autofocus: true },
          { key: "cashier", label: "Cashier Name", required: true },
        ],
        note: "Payment mode: " + f.payment_mode,
        validate: (v) => {
          const s = v.amount.trim();
          if (!s) return "Enter an amount.";
          if (L.safeFloat(s) <= 0) return "The amount must be greater than zero.";
          if (!v.cashier.trim()) return "Cashier Name is required.";
          return null;
        },
        onSubmit: async (v) => {
          const rentalId = f.rental_id;
          const amt = L.safeFloat(v.amount.trim());
          const snap = snapshot();
          if (isRefund) snap.refund = L.fmt2(L.safeFloat(f.refund) + amt);
          else snap.amount_paid = L.fmt2(L.safeFloat(f.amount_paid) + amt);
          snap.balance = L.fmt2(netFor(Object.assign({}, snap, { advance: f.advance })));
          const r = await run("return_add_payment", {
            kind, rental_id: rentalId, amount: amt, cashier_name: v.cashier.trim(),
            payment_mode: f.payment_mode, fields: snap, steppers: stepperValues(),
          });
          if (r === FAIL) return false;
          await load(rentalId);
          reloadAll();
          return true;
        },
      });
    }

    async function onSplit() {
      const rentalId = f.rental_id;
      if (!rentalId) return;
      const qty = [];
      let idx = 0;
      for (const q of rentedQty) {
        if (L.safeInt(q) > 0 && idx < 5) { qty.push(L.safeInt(steppers[idx].value)); idx++; }
        else qty.push(0);
      }
      if (qty.every((q) => q === 0)) { await alertBox("warning", "Split Error", "You haven't marked any items as returned."); return; }
      if (checkFullyReturned()) { await alertBox("warning", "Split Error", "You are returning EVERYTHING. Just click Submit."); return; }
      const cashier = await askCashier("Split & Close", "Split & Close");
      if (cashier === null) return;
      const ok = await confirmBox("Confirm Split", "This will keep returned quantities in THIS bill, and move remaining items to a NEW bill.\nProceed?");
      if (!ok) return;
      const r = await run("return_split", { rental_id: rentalId, qty_to_return: qty, fields: snapshot(), cashier_name: cashier });
      if (r === FAIL) return;
      await alertBox("success", "Success", r.message);
      await load(rentalId);
      reloadAll();
    }

    async function onPrint(image) {
      if (!f.rental_id) return;
      await run("return_print", { rental_id: f.rental_id, image_path: image, fields: snapshot() });
    }

    const unfreeze = () => setState("normal");
    const usedSteppers = computed(() => steppers.filter((s) => s.label));
    const histRows = computed(() => history[histMode.value] || []);

    return { f, info, dedDays, steppers, usedSteppers, steppersEnabled, frozen, balColor, histMode, histRows,
      onDateTime, onDamage, onDeductionField, onDeductionDays, validateStepper, inc, dec,
      onSubmitClick, openMoney, onSplit, onPrint, unfreeze };
  },
  template: `
  <div class="card">
    <div class="card-head">
      <h3><Icon name="undo"/>Return Processing</h3>
      <span v-if="f.rental_id" class="pill blue">{{ info.bill_no }} · {{ info.name }}</span>
      <span v-else class="t-muted" style="font-size:12.5px">Select a bill to process its return</span>
      <span class="spacer"></span>
      <span v-if="f.rental_id && frozen" class="pill green"><Icon name="check" size="sm"/>Settled</span>
    </div>
    <div class="card-body">
      <div v-if="frozen" class="frozen-note">
        <Icon name="lock" size="sm"/>All items returned and the balance is settled. The return is locked.
        <button class="btn sm" @click="unfreeze"><Icon name="edit" size="sm"/>Edit Return (Unfreeze)</button>
      </div>
      <div class="return-grid">
        <div class="ret-fields">
          <div class="field"><label>Return Date</label>
            <div class="with-btn">
              <input class="input tnum" data-f="ret.date" v-model="f.date" :disabled="frozen" @input="onDateTime" @blur="onDateTime" placeholder="dd-mm-yy">
              <DatePicker icon-only :model-value="f.date" :disabled="frozen" @change="v => { f.date = v; onDateTime(); }"/>
            </div>
          </div>
          <div class="field"><label>Return Time</label><input class="input tnum" data-f="ret.time" v-model="f.time" :disabled="frozen" @input="onDateTime" @blur="onDateTime" placeholder="hh:mm AM"></div>
          <div class="field"><label>Rental Days</label><input class="input num" data-f="ret.rental_days" :value="f.rental_days" readonly></div>
          <div class="field"><label>Due Amount</label><input class="input num readonly-strong" data-f="ret.due" :value="f.due" readonly></div>

          <div class="field"><label>Damage</label><input class="input num" data-f="ret.damage" v-model="f.damage" :disabled="frozen" @input="onDamage"></div>
          <div class="field"><div class="flabel"><span>Deduction</span>
              <span class="ded-days" style="margin-left:auto"><input class="input center" data-f="ret.deduction_days" v-model="dedDays" :disabled="frozen" @input="onDeductionDays" placeholder="days" title="Deduct this many days of rent"></span></div>
            <input class="input num" data-f="ret.deduction" v-model="f.deduction" :disabled="frozen" @input="onDeductionField">
          </div>
          <div class="field"><label>Advance</label><input class="input num" data-f="ret.advance" :value="f.advance" readonly></div>
          <div class="field"><label>Past Due</label><input class="input num t-red" data-f="ret.past_due" :value="f.past_due" readonly></div>

          <div class="field"><label>Payment Mode</label>
            <Seg v-model="f.payment_mode" data-f="ret.payment_mode" :disabled="frozen" :options="[{value:'Cash',label:'Cash'},{value:'UPI',label:'UPI'}]"/>
          </div>
          <div class="field"><div class="flabel">Refund
              <button class="btn ghost sm icon-only mini-add" title="Add refund" :disabled="frozen" @click="openMoney('refund')"><Icon name="plus" size="sm"/></button></div>
            <input class="input num t-purple" data-f="ret.refund" :value="f.refund" readonly>
          </div>
          <div class="field"><div class="flabel">Paid Now
              <button class="btn ghost sm icon-only mini-add" title="Add installment payment" :disabled="frozen" @click="openMoney('payment')"><Icon name="plus" size="sm"/></button></div>
            <input class="input num" data-f="ret.amount_paid" :value="f.amount_paid" readonly>
          </div>
          <div class="balance-box" :class="balColor">
            <span class="bl">Net Balance</span><span class="bv" data-f="ret.balance">₹ {{ f.balance }}</span>
          </div>
        </div>
        <div class="ret-two">
          <div class="subcard">
            <div class="subcard-head"><Icon name="package" size="sm"/>Return Quantities</div>
            <div class="subcard-body">
              <div v-if="!usedSteppers.length" class="t-muted" style="padding:6px 0">No items loaded.</div>
              <div v-for="(s, i) in usedSteppers" :key="i" class="stepper-row">
                <span class="s-label" :title="s.label">{{ s.label }}</span>
                <div class="stepper">
                  <button :disabled="!steppersEnabled" @click="dec(s)"><Icon name="minus" size="sm"/></button>
                  <input v-model="s.value" data-f="ret.stepper" :disabled="!steppersEnabled" @input="validateStepper(s)">
                  <button :disabled="!steppersEnabled" @click="inc(s)"><Icon name="plus" size="sm"/></button>
                </div>
              </div>
            </div>
          </div>
          <div class="subcard">
            <div class="subcard-head"><Icon name="history" size="sm"/>Payment History<span class="spacer"></span>
              <Seg v-model="histMode" :options="[{value:'Refund',label:'Refund'},{value:'Paid',label:'Paid'},{value:'Return',label:'Return'}]"/>
            </div>
            <div class="subcard-body" style="max-height:150px;overflow:auto;padding-top:2px">
              <table class="mini">
                <thead><tr><th>Date &amp; Time</th><th style="text-align:right">Amount</th><th>Mode</th><th>Cashier</th></tr></thead>
                <tbody>
                  <tr v-for="(h, i) in histRows" :key="i"><td class="tnum">{{ h[0] }}</td><td class="num" style="text-align:right">{{ h[1] }}</td><td>{{ h[2] }}</td><td>{{ h[3] }}</td></tr>
                  <tr v-if="!histRows.length"><td colspan="4" class="t-muted">No entries.</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
      <div class="ret-actions">
        <button class="btn primary" :disabled="frozen" @click="onSubmitClick"><Icon name="check" size="sm"/>Submit Return</button>
        <button class="btn" :disabled="frozen" @click="onSplit"><Icon name="scissors" size="sm"/>Split &amp; Close</button>
        <span style="flex:1"></span>
        <button class="btn" @click="onPrint('Estimate-Bill.png')"><Icon name="file" size="sm"/>Estimate</button>
        <button class="btn" @click="onPrint('Tax-Invoice.png')"><Icon name="receipt" size="sm"/>Tax Invoice</button>
      </div>
    </div>
  </div>`,
};

// ======================================================================== Billing page
const BillingPage = {
  components: { Icon, Seg, DatePicker, DataTable, ReturnPanel, Search },
  props: { active: Boolean },
  setup(props) {
    const blankForm = () => ({
      bill_no: "", name: "", phone: "", phone2: "", address: "", id_proof: "", vehicle: "",
      total: "0.00", advance: "", date: todayStr(), time: nowTimeStr(), payment_mode: "Cash", cashier_name: "",
      mode: "new", record_id: "", balance: "0.00", past_due: "0.00", pending: "No",
    });
    const blankRow = () => ({ code: "", name: "", spare: false, qty: "", rent: "" });
    const f = reactive(blankForm());
    const rows = reactive(Array.from({ length: MAX_MACHINES }, blankRow));
    const locked = ref(false);
    const scanStatus = ref("");
    const sug = reactive({ phone: [], phone2: [], open: "", hi: -1 });
    const nameSug = reactive({ row: -1, items: [], hi: -1 });

    // ---------------------------------------------------------------- totals & balance
    function calculateFormBalance() {
      if (f.mode === "edit") return;
      f.balance = L.fmt2(L.safeFloat(f.total) - L.safeFloat(f.advance));
    }
    function updateTotal() {
      f.total = L.fmt2(L.pySum(rows.map((r) => L.safeFloat(r.rent || 0))));
      calculateFormBalance();
    }
    function setRent(i, value) { rows[i].rent = value; updateTotal(); }

    // ---------------------------------------------------------------- machine rows
    function onQty(i) {
      const code = rows[i].code.trim();
      const mat = code ? materialByCode(code) : null;
      if (mat) {
        let q = L.pyInt(rows[i].qty);
        if (q === null) q = 0;
        setRent(i, L.pyFloatStr(mat.price * q));
      }
    }
    function onCode(i) {
      const code = rows[i].code.trim().toUpperCase();
      const mat = code ? materialByCode(code) : null;
      if (mat) {
        rows[i].name = mat.name;
        if (!rows[i].qty) { rows[i].qty = "1"; onQty(i); }
        let q = L.pyInt(rows[i].qty);
        if (q === null) q = 1;
        setRent(i, L.pyFloatStr(mat.price * q));
      }
    }
    function fillFromName(i, searchName) {
      const lower = searchName.toLowerCase();
      const mat = store.materials.find((m) => m.name.toLowerCase() === lower);
      if (!mat) return;
      rows[i].code = mat.code;
      if (!rows[i].qty) { rows[i].qty = "1"; onQty(i); }
      let q = L.pyInt(rows[i].qty);
      if (q === null) q = 1;
      setRent(i, L.pyFloatStr(mat.price * q));
    }
    function onName(i) {
      const name = rows[i].name.trim();
      if (name) {
        const lower = name.toLowerCase();
        const matches = store.materials.filter((m) => m.name.toLowerCase().includes(lower)).map((m) => m.name);
        nameSug.row = matches.length ? i : -1;
        nameSug.items = matches; nameSug.hi = -1;
      } else {
        nameSug.row = -1;
      }
      fillFromName(i, name);
    }
    function pickName(i, name) {
      rows[i].name = name;
      nameSug.row = -1;
      fillFromName(i, name);
    }
    function nameKey(i, e) {
      if (nameSug.row !== i || !nameSug.items.length) return;
      if (e.key === "ArrowDown") { e.preventDefault(); nameSug.hi = Math.min(nameSug.items.length - 1, nameSug.hi + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); nameSug.hi = Math.max(0, nameSug.hi - 1); }
      else if (e.key === "Enter" && nameSug.hi >= 0) { e.preventDefault(); pickName(i, nameSug.items[nameSug.hi]); }
      else if (e.key === "Escape") { nameSug.row = -1; }
    }
    const hideNameSug = () => setTimeout(() => { nameSug.row = -1; }, 150);

    // ---------------------------------------------------------------- phone lookups
    let phoneSeq = 0;
    function applyInfo(info) {
      if ("balance" in info) f.balance = info.balance;
      if ("past_due" in info) f.past_due = info.past_due;
      if ("pending" in info) f.pending = info.pending;
    }
    const fetchPhone = debounce(async (seq, phone) => {
      try {
        const [list, info] = await Promise.all([
          phone.trim().length >= 3 ? api("phone_suggestions", { query: phone }) : Promise.resolve([]),
          api("phone_info", { phone }),
        ]);
        if (seq !== phoneSeq) return;
        sug.phone = list; sug.hi = -1;
        sug.open = list.length && document.activeElement && document.activeElement.dataset.sug === "phone" ? "phone" : (sug.open === "phone" ? "" : sug.open);
        applyInfo(info);
      } catch (e) { /* lookups are best-effort, like the Tk traces */ }
    }, 120);
    function onPhone() { phoneSeq++; fetchPhone(phoneSeq, f.phone); }
    let phone2Seq = 0;
    const fetchPhone2 = debounce(async (seq, q) => {
      try {
        const list = q.trim().length >= 3 ? await api("phone_suggestions", { query: q, second: true }) : [];
        if (seq !== phone2Seq) return;
        sug.phone2 = list; sug.hi = -1;
        sug.open = list.length ? "phone2" : (sug.open === "phone2" ? "" : sug.open);
      } catch (e) { /* ignore */ }
    }, 120);
    function onPhone2() { phone2Seq++; fetchPhone2(phone2Seq, f.phone2); }
    async function pickCustomer(item, second) {
      phoneSeq++; phone2Seq++;
      sug.open = "";
      const r = await run("pick_customer", { key: item.key, second });
      if (r === FAIL || !r) return;
      f.phone = r.phone; f.name = r.name; f.address = r.address; f.phone2 = r.phone2;
      f.past_due = r.past_due; f.balance = r.balance;
      if ("pending" in r) f.pending = r.pending;
    }
    function sugKey(which, e) {
      const list = sug[which];
      if (sug.open !== which || !list.length) return;
      if (e.key === "ArrowDown") { e.preventDefault(); sug.hi = Math.min(list.length - 1, sug.hi + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); sug.hi = Math.max(0, sug.hi - 1); }
      else if (e.key === "Enter" && sug.hi >= 0) { e.preventDefault(); pickCustomer(list[sug.hi], which === "phone2"); }
      else if (e.key === "Escape") { sug.open = ""; }
    }
    const hideSug = () => setTimeout(() => { sug.open = ""; }, 150);

    // ---------------------------------------------------------------- scanner
    const camera = ref(null);
    async function onPhoto(ev) {
      const file = ev.target.files && ev.target.files[0];
      ev.target.value = "";
      if (!file) return;
      scanStatus.value = "scanning";
      const b64 = await new Promise((res, rej) => {
        const fr = new FileReader();
        fr.onload = () => res(String(fr.result).split(",")[1]);
        fr.onerror = rej;
        fr.readAsDataURL(file);
      });
      const r = await run("upload_id_photo", { bill_no: f.bill_no, name: f.name.trim(), id_type: f.id_proof.trim(), data_b64: b64 });
      if (r === FAIL) { scanStatus.value = ""; return; }
      scanStatus.value = "saved";
      await alertBox("success", "Photo Saved 🎉", r.message);
    }
    async function onScan() {
      const bill = f.bill_no, name = f.name.trim(), idType = f.id_proof.trim();
      if (!name || !idType) {
        await alertBox("warning", "Incomplete Data", "Please enter the Customer Name and ID Proof Type (e.g. 'Aadhar') before scanning!");
        return;
      }
      if (IS_WEB) { camera.value.click(); return; }
      scanStatus.value = "scanning";
      const r = await run("scan_id", { bill_no: bill, name, id_type: idType });
      if (r === FAIL) { scanStatus.value = ""; return; }
      if (r.status === "saved") {
        scanStatus.value = "saved";
        await alertBox("success", "Scan Successful! 🎉", r.message);
      } else {
        scanStatus.value = "";
      }
    }

    // ---------------------------------------------------------------- form actions
    async function clearForm() {
      locked.value = false;
      Object.assign(f, blankForm());
      if (store.user && store.user.display_name) f.cashier_name = store.user.display_name;  // signed-in person (editable)
      rows.forEach((r) => Object.assign(r, blankRow()));
      scanStatus.value = "";
      sug.open = ""; nameSug.row = -1;
      phoneSeq++; phone2Seq++;
      selectedBill.value = null;
      const seq = ++billSeq;
      try {
        const b = await api("next_bill_no");
        if (seq === billSeq && f.mode === "new") f.bill_no = b;
      } catch (e) { if (seq === billSeq && f.mode === "new") f.bill_no = "A00001"; }
    }
    let billSeq = 0;

    async function submit() {
      const payload = { form: Object.assign({}, f), rows: rows.map((r) => Object.assign({}, r)) };
      const r = await run("submit_form", { payload });
      if (r === FAIL) return;
      await alertBox("success", "Success", r.message);
      await clearForm();
      reloadAll();
    }
    async function cancelRental() {
      if (!f.record_id) { await alertBox("warning", "No Selection", "Please select a rental to cancel."); return; }
      const ok = await confirmBox("Confirm Cancellation", "Cancel this rental? Undo is not possible.", { kind: "danger", okText: "Cancel Rental", cancelText: "Keep" });
      if (!ok) return;
      const r = await run("cancel_record", { record_id: f.record_id });
      if (r === FAIL) return;
      await alertBox("success", "Success", r.message);
      await clearForm();
      reloadAll();
    }
    async function printBill(image) {
      if (!selectedBill.value) { await alertBox("warning", "Error", "No record selected"); return; }
      await run("print_bill", { bill_no: selectedBill.value, image_path: image });
    }
    async function backup() {
      // "Sync": upload this computer's changes to the cloud now (Supabase is the backup)
      if ((await run("sync_now")) !== FAIL) toast("info", "Syncing", "Uploading changes to the cloud…", 3000);
    }

    // ---------------------------------------------------------------- records table
    const filt = reactive({ search: "", status: "all", from_date: "", to_date: "", from_bill: "", to_bill: "" });
    const tableRows = ref([]);
    const selectedBill = ref(null);
    const tableLoading = ref(false);
    let tableSeq = 0;
    async function loadTable() {
      const seq = ++tableSeq;
      tableLoading.value = true;
      try {
        const data = await api("outward_table", Object.assign({}, filt));
        if (seq !== tableSeq) return;
        tableRows.value = data;
        if (selectedBill.value && !data.some((r) => r.values[0] === selectedBill.value)) selectedBill.value = null;
      } catch (e) {
        if (seq === tableSeq) await alertBox("error", e.title || "Error", e.message);
      } finally {
        if (seq === tableSeq) tableLoading.value = false;
      }
    }
    const loadTableSoon = debounce(loadTable, 250);
    watch(() => filt.search, loadTableSoon);
    watch(() => [filt.status, filt.from_date, filt.to_date], loadTable);
    watch(() => [filt.from_bill, filt.to_bill], loadTableSoon);
    function clearFilters() { Object.assign(filt, { search: "", status: "all", from_date: "", to_date: "", from_bill: "", to_bill: "" }); }
    useReload(props, loadTable);

    let selectSeq = 0;
    async function selectRow(row) {
      const bill = row.values[0];
      selectedBill.value = bill;
      const seq = ++selectSeq;
      const r = await run("select_record", { bill_no: bill });
      if (seq !== selectSeq || r === FAIL || !r) return;
      phoneSeq++; phone2Seq++;
      sug.open = ""; nameSug.row = -1;
      Object.assign(f, r.form);
      f.mode = "edit";
      rows.forEach((row, i) => Object.assign(row, r.items[i] || blankRow()));
      // setting the item rents re-totals "Daily Rent", exactly like the Tk traces did
      f.total = L.fmt2(L.pySum(rows.map((x) => L.safeFloat(x.rent || 0))));
      applyInfo(r);
      bus.emit("return:load", r.form.record_id, r.ret);
      locked.value = true;
    }
    async function printList() {
      await run("print_outward_list", { rows: tableRows.value.map((r) => r.values) });
    }

    const columns = [
      { idx: 0, label: "Bill No", width: "116px", cls: () => "strong num" },
      { idx: 1, label: "Name", width: "150px" },
      { idx: 2, label: "Phone", width: "124px", cls: () => "num" },
      { idx: 3, label: "Phone 2", width: "124px", cls: () => "num" },
      { idx: 4, label: "Address" },
      { idx: 5, label: "Date", width: "96px", cls: () => "num" },
      { idx: 6, label: "Balance", width: "100px", align: "r", cls: (r) => "num t-strong " + (L.safeFloat(r.values[6]) > 0 ? "t-red" : (L.safeFloat(r.values[6]) < 0 ? "t-purple" : "t-green")) },
      { idx: 7, label: "Pending", width: "82px", align: "c" },
    ];

    // Global shortcuts (Ctrl+N / Ctrl+S / Ctrl+P were bound with bind_all in Tk)
    window.BillingActions = { clear: clearForm, submit, print: () => printBill("bill-layout.jpg") };
    onMounted(clearForm);

    return { f, rows, locked, scanStatus, sug, nameSug, filt, tableRows, selectedBill, tableLoading, columns,
      updateTotal, calculateFormBalance, onCode, onQty, onName, pickName, nameKey, hideNameSug,
      onPhone, onPhone2, pickCustomer, sugKey, hideSug, onScan, onPhoto, camera, isWeb: IS_WEB, clearForm, submit, cancelRental, printBill, backup,
      clearFilters, selectRow, printList, hasStar, stripStar };
  },
  template: `
  <div class="billing">
    <!-- ================= LEFT: bill form ================= -->
    <div class="billing-left">
      <div class="card">
        <div class="card-head">
          <div class="bill-head">
            <span class="t-muted" style="font-size:12px;font-weight:600">BILL</span>
            <span class="bill-no" data-f="bill_no">{{ f.bill_no || '—' }}</span>
            <span v-if="f.mode === 'edit'" class="pill amber"><span class="dot"></span>Saved bill</span>
            <span v-else class="pill green"><span class="dot"></span>New bill</span>
          </div>
          <span class="spacer"></span>
          <button class="btn sm" @click="clearForm" title="Start a new bill (Ctrl+N)"><Icon name="plus" size="sm"/>New</button>
        </div>
        <div class="card-body" style="display:flex;flex-direction:column;gap:12px">
          <div v-if="locked" class="lockbar"><Icon name="lock" size="sm"/>Viewing a saved bill. Fields are locked.
            <button class="btn sm" @click="locked = false"><Icon name="edit" size="sm"/>Edit Record</button>
          </div>
          <div class="form-grid">
            <div class="field span-2"><label>Customer Name<span class="req">*</span></label>
              <input class="input" data-f="name" v-model="f.name" :disabled="locked" placeholder="Enter customer full name"></div>
            <div class="field suggest-anchor"><label>Phone<span class="req">*</span></label>
              <input class="input tnum" data-f="phone" v-model="f.phone" :disabled="locked" data-sug="phone" placeholder="10-digit mobile"
                     @input="onPhone" @keydown="sugKey('phone', $event)" @blur="hideSug" @focus="sug.phone.length && f.phone.trim().length >= 3 ? sug.open = 'phone' : null">
              <div v-if="sug.open === 'phone' && sug.phone.length" class="suggest">
                <button v-for="(s, i) in sug.phone" :key="s.label" :class="{ hi: i === sug.hi }" @mousedown.prevent="pickCustomer(s, false)">
                  <span class="tnum">{{ s.phone }}</span><span class="s-sub">{{ s.name }}</span></button>
              </div>
            </div>
            <div class="field suggest-anchor"><label>Phone 2</label>
              <input class="input tnum" data-f="phone2" v-model="f.phone2" :disabled="locked" placeholder="Optional"
                     @input="onPhone2" @keydown="sugKey('phone2', $event)" @blur="hideSug">
              <div v-if="sug.open === 'phone2' && sug.phone2.length" class="suggest">
                <button v-for="(s, i) in sug.phone2" :key="s.label" :class="{ hi: i === sug.hi }" @mousedown.prevent="pickCustomer(s, true)">
                  <span class="tnum">{{ s.phone }}</span><span class="s-sub">{{ s.name }}</span></button>
              </div>
            </div>
            <div class="field span-2"><label>Address</label>
              <textarea class="textarea" data-f="address" rows="2" v-model="f.address" :disabled="locked"></textarea></div>
            <div class="field span-2"><label>ID Proof</label>
              <div class="with-btn" style="align-items:center">
                <input class="input" data-f="id_proof" v-model="f.id_proof" :disabled="locked" placeholder="e.g. Aadhar">
                <button class="btn" :disabled="locked || scanStatus === 'scanning'" @click="onScan" :title="isWeb ? 'Take a photo of the ID proof' : 'Scan the ID proof'"><Icon name="scan" size="sm"/>{{ isWeb ? 'Photo' : 'Scan' }}</button>
                <input ref="camera" type="file" accept="image/*" capture="environment" style="display:none" @change="onPhoto">
                <span v-if="scanStatus === 'scanning'" class="scan-status" style="color:var(--warning-text)">Scanning…</span>
                <span v-else-if="scanStatus === 'saved'" class="scan-status" style="color:var(--success-text)">✓ Saved</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><h3><Icon name="package"/>Machine Details</h3></div>
        <div class="card-body" style="padding-top:10px">
          <table class="machine-table">
            <thead><tr><th></th><th style="width:64px">Code</th><th>Machine Name</th><th style="width:42px;text-align:center">Spare</th><th style="width:54px">Qty</th><th style="width:86px">Rent/Day</th></tr></thead>
            <tbody>
              <tr v-for="(r, i) in rows" :key="i">
                <td class="idx">{{ i + 1 }}</td>
                <td><input class="input" data-f="row.code" v-model="r.code" :disabled="locked" @input="onCode(i)"></td>
                <td class="suggest-anchor">
                  <input class="input" data-f="row.name" v-model="r.name" :disabled="locked" @input="onName(i)" @keydown="nameKey(i, $event)" @blur="hideNameSug">
                  <div v-if="nameSug.row === i" class="suggest">
                    <button v-for="(n, k) in nameSug.items" :key="n + k" :class="{ hi: k === nameSug.hi }" @mousedown.prevent="pickName(i, n)">{{ n }}</button>
                  </div>
                </td>
                <td style="text-align:center"><label class="check" style="justify-content:center"><input type="checkbox" data-f="row.spare" v-model="r.spare" :disabled="locked"></label></td>
                <td><input class="input num" data-f="row.qty" v-model="r.qty" :disabled="locked" @input="onQty(i)"></td>
                <td><input class="input num" data-f="row.rent" v-model="r.rent" :disabled="locked" @input="updateTotal"></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><h3><Icon name="wallet"/>Summary</h3></div>
        <div class="card-body" style="display:flex;flex-direction:column;gap:12px">
          <div class="form-grid">
            <div class="field"><label>Date</label>
              <div class="with-btn"><input class="input tnum" data-f="date" v-model="f.date" :disabled="locked" placeholder="dd-mm-yy">
                <DatePicker icon-only :model-value="f.date" :disabled="locked" @change="v => f.date = v"/></div></div>
            <div class="field"><label>Time</label><input class="input tnum" data-f="time" v-model="f.time" :disabled="locked" placeholder="hh:mm AM"></div>
            <div class="field"><label>Vehicle No.</label><input class="input" data-f="vehicle" v-model="f.vehicle" :disabled="locked"></div>
            <div class="field"><label>Cashier Name<span class="req">*</span></label><input class="input" data-f="cashier_name" v-model="f.cashier_name" :disabled="locked"></div>
            <div class="field"><label>Daily Rent</label><input class="input num" data-f="total" v-model="f.total" :disabled="locked" @input="calculateFormBalance"></div>
            <div class="field"><label>Advance Paid</label><input class="input num" data-f="advance" v-model="f.advance" :disabled="locked" @input="calculateFormBalance"></div>
            <div class="field"><label>Advance Mode</label>
              <Seg v-model="f.payment_mode" data-f="payment_mode" :disabled="locked" :options="[{value:'Cash',label:'Cash'},{value:'UPI',label:'UPI'}]"/></div>
          </div>
          <div class="form-grid three">
            <div class="balance-box" :class="f.pending === 'Yes' ? 'amber' : ''"><span class="bl">Pending Returns</span><span class="bv" data-f="pending" style="font-size:15px">{{ f.pending }}</span></div>
            <div class="balance-box" :class="parseFloat(f.past_due) > 0 ? 'red' : ''"><span class="bl">Past Due</span><span class="bv" data-f="past_due" style="font-size:15px">₹ {{ f.past_due }}</span></div>
            <div class="balance-box" :class="parseFloat(f.balance) > 0 ? 'red' : (parseFloat(f.balance) < 0 ? '' : 'green')"><span class="bl">Balance Due</span><span class="bv" data-f="balance" style="font-size:15px">₹ {{ f.balance }}</span></div>
          </div>
          <div class="action-bar">
            <button class="btn primary" @click="submit" title="Ctrl+S"><Icon name="save" size="sm"/>Submit</button>
            <button class="btn" @click="clearForm" title="Ctrl+N"><Icon name="eraser" size="sm"/>Clear</button>
            <button class="btn danger" @click="cancelRental"><Icon name="ban" size="sm"/>Cancel</button>
            <button class="btn" @click="printBill('Estimate-Bill.png')"><Icon name="file" size="sm"/>Estimate</button>
            <button class="btn" @click="printBill('Tax-Invoice.png')"><Icon name="receipt" size="sm"/>Tax Inv.</button>
            <button class="btn" @click="backup" title="Upload to the cloud now (Ctrl+B)"><Icon name="cloud" size="sm"/>Sync</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ================= RIGHT: records + returns ================= -->
    <div class="billing-right" style="overflow-y:auto;padding-bottom:2px">
      <div class="card" style="display:flex;flex-direction:column;min-height:340px;flex:1 0 340px">
        <div class="card-head" style="gap:10px">
          <Search v-model="filt.search" placeholder="Search name, phone, address, bill" width="100%" style="flex:1;min-width:180px"/>
          <Seg v-model="filt.status" :options="[{value:'all',label:'All'},{value:'pending',label:'Pending Returns'},{value:'balance',label:'Balance Due'}]"/>
          <button class="btn" @click="printList" title="Print List"><Icon name="printer" size="sm"/>Print</button>
        </div>
        <div class="toolbar" style="padding:9px 16px;border-bottom:1px solid var(--border);flex-wrap:nowrap;overflow-x:auto">
          <span class="tb-label">Date</span>
          <DatePicker v-model="filt.from_date" placeholder="From" clearable small/>
          <DatePicker v-model="filt.to_date" placeholder="To" clearable small/>
          <span class="divider"></span>
          <span class="tb-label" style="white-space:nowrap">Bill No</span>
          <input class="input tnum" style="width:84px;height:28px;flex:none" v-model="filt.from_bill" placeholder="From">
          <input class="input tnum" style="width:84px;height:28px;flex:none" v-model="filt.to_bill" placeholder="To">
          <span class="grow"></span>
          <button class="btn ghost sm" @click="clearFilters"><Icon name="x" size="sm"/>Clear Filters</button>
        </div>
        <DataTable :columns="columns" :rows="tableRows" :row-key="r => r.values[0]" :selected-key="selectedBill" selectable min-width="920px"
                   @select="selectRow" empty-text="No bills match these filters.">
          <template #cell-0="{ row, value }"><span class="status-dot" :class="row.tag === 'returned' ? 'ok' : 'open'"></span>{{ value }}</template>
          <template #cell-1="{ value }">{{ stripStar(value) }}<span v-if="hasStar(value)" class="star"> ★</span></template>
          <template #cell-7="{ value }"><span class="pill" :class="value === 'Yes' ? 'amber' : 'green'">{{ value }}</span></template>
        </DataTable>
        <div class="table-foot"><span>{{ tableRows.length }} bills</span><span v-if="tableLoading">· Loading…</span>
          <span style="margin-left:auto;display:flex;gap:14px;align-items:center"><span><span class="status-dot ok"></span>Returned &amp; settled</span><span><span class="status-dot open"></span>Open</span></span></div>
      </div>
      <ReturnPanel/>
    </div>
  </div>`,
};

window.BillingPage = BillingPage;

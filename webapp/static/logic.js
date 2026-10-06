// logic.js - Exact JavaScript ports of the small Python helpers the forms use
// while typing (utils.safe_float/safe_int, calculate_master_balance, the return
// form's rental-day counter, Python number formatting).
// Kept dependency-free so it can be checked against Python in tests.
(function (root) {
  "use strict";

  // Python float() on a string that only contains digits, '.' and '-'
  function pyFloatFromCleaned(s) {
    if (!/^-?(\d+\.?\d*|\.\d+)$/.test(s)) return null;
    return Number(s);
  }

  // utils.safe_float
  function safeFloat(val, dflt) {
    if (dflt === undefined) dflt = 0.0;
    if (val === null || val === undefined) return dflt;
    let result;
    if (typeof val === "string") {
      let s = val.trim();
      if (!s) return dflt;
      s = s.replace(/[^\d.-]/g, "");
      result = pyFloatFromCleaned(s);
      if (result === null) return dflt;
    } else if (typeof val === "boolean") {
      result = val ? 1 : 0;
    } else {
      result = Number(val);
    }
    if (result !== result) return dflt; // NaN
    return result;
  }

  // utils.safe_int
  function safeInt(val, dflt) {
    if (dflt === undefined) dflt = 0;
    if (val === null || val === undefined) return dflt;
    let f;
    if (typeof val === "string") {
      let s = val.trim();
      if (!s) return dflt;
      s = s.replace(/[^\d]/g, "");
      if (!s) return dflt;
      f = Number(s);
    } else if (typeof val === "boolean") {
      f = val ? 1 : 0;
    } else {
      f = Number(val);
    }
    if (!isFinite(f)) return dflt; // int(float('nan'/'inf')) raises -> default
    return Math.trunc(f) + 0; // +0 turns -0 into 0
  }

  // Python int(str): returns null where Python raises ValueError
  function pyInt(str) {
    const s = String(str).trim();
    if (!/^[+-]?\d+(_\d+)*$/.test(s)) return null;
    return parseInt(s.replace(/_/g, ""), 10) + 0;
  }

  // Python f"{x:.2f}" (round-half-even on exact binary ties, keeps "-0.00")
  function fmt2(x) {
    x = Number(x);
    if (x !== x) return "nan";
    if (x === Infinity) return "inf";
    if (x === -Infinity) return "-inf";
    const neg = x < 0 || Object.is(x, -0);
    const a = Math.abs(x);
    const eighths = a * 8;
    if (Number.isInteger(eighths) && eighths % 2 === 1 && a < 1e15) {
      // exact tie at the third decimal (x = odd/8): Python rounds half to even
      let n = Math.floor(a * 100);
      if (n % 2 === 1) n += 1;
      const ip = Math.floor(n / 100), fp = n % 100;
      return (neg ? "-" : "") + ip + "." + (fp < 10 ? "0" : "") + fp;
    }
    return (neg ? "-" : "") + a.toFixed(2);
  }

  // Python f"{x:,.2f}"
  function fmtComma2(x) {
    const s = fmt2(x);
    const m = /^(-?)(\d+)(\.\d+)?$/.exec(s);
    if (!m) return s;
    return m[1] + m[2].replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (m[3] || "");
  }

  // Python str(float) for ordinary values (100.0 -> "100.0")
  function pyFloatStr(x) {
    x = Number(x);
    if (x !== x) return "nan";
    if (!isFinite(x)) return x > 0 ? "inf" : "-inf";
    if (Number.isInteger(x) && Math.abs(x) < 1e16) return (x < 0 || Object.is(x, -0) ? "-" : "") + Math.abs(x).toFixed(1);
    return String(x);
  }

  // shared_imports.calculate_master_balance -> [due_amount, net_balance]
  function masterBalance(o) {
    const rent = safeFloat(o.daily_rent);
    const days = Math.max(1, safeInt(o.rental_days));
    const adv = safeFloat(o.advance_paid);
    const inst = safeFloat(o.installments_paid === undefined ? 0.0 : o.installments_paid);
    const dmg = safeFloat(o.damage_charges === undefined ? 0.0 : o.damage_charges);
    const deduct = safeFloat(o.discount_deduction === undefined ? 0.0 : o.discount_deduction);
    const paid = safeFloat(o.final_amount_paid === undefined ? 0.0 : o.final_amount_paid);
    const ref = safeFloat(o.refund_given === undefined ? 0.0 : o.refund_given);
    const ov = o.manual_due_override;
    let due;
    if (ov !== null && ov !== undefined && String(ov).trim() !== "") due = safeFloat(ov);
    else due = rent * days;
    const totalPaid = Math.max(inst, paid);
    let net;
    if (o.is_returned) net = (due + dmg) - (adv + totalPaid + deduct) + ref;
    else net = due - (adv + totalPaid);
    return [due, net];
  }

  // datetime.strptime(s, "%d-%m-%y %I:%M %p") -> epoch ms (UTC) or null
  const DT_RE = /^(3[0-1]|[1-2]\d|0[1-9]|[1-9]| [1-9])-(1[0-2]|0[1-9]|[1-9])-(\d\d)\s+(1[0-2]|0[1-9]|[1-9]):([0-5]\d|\d)\s+(am|pm)$/i;
  function parseDmyImp(s) {
    const m = DT_RE.exec(s);
    if (!m) return null;
    const day = parseInt(m[1], 10), month = parseInt(m[2], 10);
    let year = parseInt(m[3], 10);
    year += year <= 68 ? 2000 : 1900;
    let hour = parseInt(m[4], 10);
    const minute = parseInt(m[5], 10);
    const pm = m[6].toLowerCase() === "pm";
    if (pm && hour !== 12) hour += 12;
    if (!pm && hour === 12) hour = 0;
    const dim = new Date(Date.UTC(year, month, 0)).getUTCDate();
    if (day > dim) return null; // datetime() raises "day is out of range"
    return Date.UTC(year, month - 1, day, hour, minute);
  }

  // return_form.calc_rental_days()
  function returnRentalDays(startDate, startTime, endDate, endTime) {
    const sp = (d, t) => (!d || !t) ? null : parseDmyImp(`${d} ${t}`);
    const start = sp(startDate, startTime), end = sp(endDate, endTime);
    if (start !== null && end !== null) {
      if (end < start) return 1;
      const ms = end - start;
      let days = Math.floor(ms / 86400000);
      const seconds = (ms - days * 86400000) / 1000;
      days = Math.max(days, 0);
      const hours = seconds / 3600;
      if (days === 0 && hours <= 24) return 1;
      if (hours > 0) days += 1;
      return Math.max(days, 1);
    }
    return 1;
  }

  // materials.get_material_by_code key normalisation
  function materialKey(code) {
    if (code === null || code === undefined) return null;
    const key = String(code).trim();
    if (/^\d+$/.test(key)) return BigInt(key).toString();
    return key.toUpperCase();
  }

  // Python sum(...) over floats (left to right, starting from 0)
  function pySum(values) {
    let t = 0;
    for (const v of values) t = t + v;
    return t;
  }

  const Logic = { safeFloat, safeInt, pyInt, fmt2, fmtComma2, pyFloatStr, masterBalance,
                  parseDmyImp, returnRentalDays, materialKey, pySum };
  if (typeof module !== "undefined" && module.exports) module.exports = Logic;
  else root.Logic = Logic;
})(typeof window !== "undefined" ? window : globalThis);

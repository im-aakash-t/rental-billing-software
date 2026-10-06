# webapp/reports.py - "Print List" PDF reports.
# Ported from the print_* functions inside each Tkinter tab. They used to read
# the rows currently shown in the Treeview; the web UI now sends those same rows.
import csv
import os
import webbrowser
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

from utils import log_error
from webapp.services import UserError


def _table_style(header_size, align, pad):
    return TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2176ff")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), align),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), header_size),
        ('BOTTOMPADDING', (0,0), (-1,0), pad),
        ('TOPPADDING', (0,0), (-1,0), pad),
        ('BACKGROUND', (0,1), (-1,-1), colors.white),
        ('GRID', (0,0), (-1,-1), 1, colors.lightgrey),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ])


def _build(filepath, elements, pagesize, margins):
    os.makedirs("reports", exist_ok=True)
    left_right, top_bottom = margins
    doc = SimpleDocTemplate(filepath, pagesize=pagesize, rightMargin=left_right, leftMargin=left_right,
                            topMargin=top_bottom, bottomMargin=top_bottom)
    doc.build(elements)
    webbrowser.open(filepath)


def _no_data(message):
    raise UserError("No Data", message, kind="info")


def outward_list(rows):
    """form_tab.print_outward_list - rows are the 8 table values."""
    if not rows:
        _no_data("There is no data to print.")
    try:
        os.makedirs("reports", exist_ok=True)
        filepath = os.path.join("reports", f"Outward_List_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
        styles = getSampleStyleSheet()
        elements = [
            Paragraph(f"<b>Outward Billing List</b> - Generated on {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", styles['Title']),
            Paragraph("<br/><br/>", styles['Normal']),
        ]
        data = [["Bill No", "Name", "Phone", "Address", "Date", "Balance", "Pending Items"]]
        for values in rows:
            addr_p = Paragraph(values[4], styles["Normal"])
            data.append([values[0], values[1], values[2], addr_p, values[5], values[6], values[7]])
        t = Table(data, colWidths=[70, 140, 100, 250, 80, 80, 80])
        t.setStyle(_table_style(11, 'LEFT', 10))
        elements.append(t)
        _build(filepath, elements, landscape(A4), (30, 30))
    except Exception as e:
        raise UserError("Print Error", f"Failed to generate report: {e}")


def pending_returns_list(records):
    """partial_returns_tab.print_search_results - records as returned by pending_returns_table."""
    if not records:
        _no_data("There are no pending returns to print.")
    try:
        os.makedirs("reports", exist_ok=True)
        filepath = os.path.join("reports", f"Pending_Returns_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
        styles = getSampleStyleSheet()
        elements = [
            Paragraph(f"<b>Pending Returns Report</b> - Generated on {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", styles['Title']),
            Paragraph("<br/><br/>", styles['Normal']),
        ]
        data = [["Bill No", "Customer Name", "Phone", "Address", "Date", "Pending Items"]]
        for rec in records:
            address = rec["address"].replace('\n', ' ')
            items_str = ", ".join(f"{i['name']} (Qty: {i['taken']})" for i in rec["items"])
            data.append([rec["bill_no"], rec["name"], rec["phone"], Paragraph(address, styles["Normal"]),
                         rec["date"], Paragraph(items_str, styles["Normal"])])
        t = Table(data, colWidths=[60, 130, 90, 200, 70, 230])
        t.setStyle(_table_style(11, 'LEFT', 10))
        elements.append(t)
        _build(filepath, elements, landscape(A4), (30, 30))
    except Exception as e:
        log_error("Print Pending Returns", e)
        raise UserError("Print Error", f"Failed to generate report: {e}")


def pending_payments_list(rows, filter_type):
    """pending_tab.print_pending_list - rows are the 8 table values."""
    if not rows:
        _no_data("There is no data to print.")
    try:
        os.makedirs("reports", exist_ok=True)
        if filter_type == "collect": title_text = "Pending Collections (Debt) Report"
        elif filter_type == "refund": title_text = "Pending Refunds Report"
        else: title_text = "All Pending Payments & Refunds Report"
        filepath = os.path.join("reports", f"Pending_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
        styles = getSampleStyleSheet()
        elements = [
            Paragraph(f"<b>{title_text}</b> - {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", styles['Title']),
            Paragraph("<br/><br/>", styles['Normal']),
        ]
        data = [["Bill No", "Name", "Phone", "Date", "Due", "Advance", "Paid", "Balance"]]
        data.extend(list(values) for values in rows)
        t = Table(data, colWidths=[70, 150, 100, 80, 80, 80, 80, 100])
        t.setStyle(_table_style(11, 'CENTER', 10))
        elements.append(t)
        _build(filepath, elements, landscape(A4), (30, 30))
    except Exception as e:
        raise UserError("Print Error", f"Failed to generate report: {e}")


def daily_ledger(rows, from_date, to_date, totals):
    """daily_report_tab.print_daily_report."""
    if not rows:
        _no_data("There are no transactions in this date range to print.")
    try:
        os.makedirs("reports", exist_ok=True)
        filepath = os.path.join("reports", f"Overview_Report_{from_date}_to_{to_date}_{datetime.now().strftime('%H%M%S')}.pdf")
        styles = getSampleStyleSheet()
        elements = [Paragraph(f"<b>Overview Report</b> - From: {from_date} To: {to_date}", styles['Title'])]
        summary_text = f"""
        <b>Rented Items:</b> {totals['rented']} | <b>Returned Items:</b> {totals['returned']}<br/>
        <b>Cash In:</b> Rs. {totals['cash_in']:.2f} | <b>Cash Out:</b> Rs. {totals['cash_out']:.2f}<br/>
        <b>UPI/GPay In:</b> Rs. {totals['gpay_in']:.2f} | <b>UPI/GPay Out:</b> Rs. {totals['gpay_out']:.2f}
        """
        elements.append(Paragraph(summary_text, styles['Normal']))
        elements.append(Paragraph("<br/><br/>", styles['Normal']))
        data = [["Date & Time", "Bill No", "Customer Name", "Transaction Type", "Details", "Amount", "Mode"]]
        data.extend(list(values) for values in rows)
        t = Table(data, colWidths=[100, 60, 140, 110, 220, 80, 60])
        t.setStyle(_table_style(10, 'LEFT', 8))
        elements.append(t)
        _build(filepath, elements, landscape(A4), (20, 30))
    except Exception as e:
        raise UserError("Print Error", f"Failed to generate report: {e}")


def customer_report_list(rows):
    """customer_report_tab.print_customer_report - rows are the 13 table values."""
    if not rows:
        _no_data("There is no data to print.")
    try:
        os.makedirs("reports", exist_ok=True)
        filepath = os.path.join("reports", f"Customer_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
        styles = getSampleStyleSheet()
        elements = [
            Paragraph(f"<b>Customer Report</b> - Generated on {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", styles['Title']),
            Paragraph("<br/><br/>", styles['Normal']),
        ]
        data = [["Bill No", "Name", "Phone", "Date", "Machines", "Total", "Adv", "Return Dt", "Paid", "Refund", "Balance"]]
        for values in rows:
            machines_p = Paragraph(values[4], styles["Normal"])
            data.append([values[0], values[1], values[2], values[3], machines_p,
                         values[5], values[6], values[8], values[9], values[10], values[12]])
        t = Table(data, colWidths=[70, 90, 80, 60, 160, 50, 50, 70, 50, 50, 60])
        t.setStyle(_table_style(10, 'CENTER', 8))
        elements.append(t)
        _build(filepath, elements, landscape(A4), (20, 30))
    except Exception as e:
        log_error("Print Customer Report", e)
        raise UserError("Print Error", f"Failed to generate report: {e}")


def customers_list(rows):
    """customers_tab.print_customers_list - rows: [name, phone, phone2, address, regular]."""
    if not rows:
        _no_data("No customers found to print.")
    try:
        os.makedirs("reports", exist_ok=True)
        filepath = os.path.join("reports", f"Customer_List_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
        styles = getSampleStyleSheet()
        elements = [
            Paragraph(f"<b>Customer Directory</b> - Generated on {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", styles['Title']),
            Paragraph("<br/><br/>", styles['Normal']),
        ]
        data = [["Name", "Phone 1", "Phone 2", "Address", "Regular?"]]
        for values in rows:
            data.append([values[0], values[1], values[2], Paragraph(values[3], styles["Normal"]), values[4]])
        t = Table(data, colWidths=[150, 100, 100, 350, 80])
        t.setStyle(_table_style(11, 'LEFT', 10))
        elements.append(t)
        _build(filepath, elements, landscape(A4), (20, 30))
    except Exception as e:
        raise UserError("Print Error", f"Failed to generate report: {e}")


def stock_list(rows):
    """analytics_dashboard.print_stock_report - silently does nothing when empty."""
    if not rows:
        return False
    try:
        os.makedirs("reports", exist_ok=True)
        filepath = os.path.join("reports", f"Stock_Status_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
        elements = [
            Paragraph(f"<b>Live Stock Status Report</b> - {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", getSampleStyleSheet()['Title']),
            Paragraph("<br/><br/>", getSampleStyleSheet()['Normal']),
        ]
        data = [["Machine Name", "Total Stock", "Currently Rented", "Available Now"]]
        data.extend(list(values) for values in rows)
        t = Table(data, colWidths=[200, 100, 100, 100])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2176ff")), ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('BOTTOMPADDING', (0,0), (-1,0), 10),
            ('TOPPADDING', (0,0), (-1,0), 10), ('BACKGROUND', (0,1), (-1,-1), colors.white), ('GRID', (0,0), (-1,-1), 1, colors.lightgrey),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
        ]))
        elements.append(t)
        _build(filepath, elements, A4, (30, 30))
        return True
    except Exception as e:
        raise UserError("Print Error", f"Failed: {e}")


def equipment_report(rows, from_date, to_date, total_revenue, top_earner, top_freq):
    """materials_report_tab.print_report - rows: first 4 values (no visual bar)."""
    if not rows:
        _no_data("There are no records to print.")
    try:
        os.makedirs("reports", exist_ok=True)
        filepath = os.path.join("reports", f"Equipment_Analytics_{from_date}_to_{to_date}_{datetime.now().strftime('%H%M%S')}.pdf")
        styles = getSampleStyleSheet()
        elements = [Paragraph(f"<b>Equipment Analytics Report</b> - From: {from_date} To: {to_date}", styles['Title'])]
        summary_text = f"<b>Total Revenue:</b> {total_revenue} &nbsp;&nbsp; | &nbsp;&nbsp; <b>Top Earner:</b> {top_earner} &nbsp;&nbsp; | &nbsp;&nbsp; <b>Most Frequent:</b> {top_freq}"
        elements.append(Paragraph(summary_text, styles['Normal']))
        elements.append(Paragraph("<br/><br/>", styles['Normal']))
        data = [["Equipment Type", "Rental Frequency (Bills)", "Total Revenue (Rs.)", "Contribution (%)"]]
        data.extend(list(values[:4]) for values in rows)
        t = Table(data, colWidths=[250, 150, 150, 150])
        t.setStyle(_table_style(10, 'LEFT', 8))
        elements.append(t)
        _build(filepath, elements, landscape(A4), (30, 30))
    except Exception as e:
        raise UserError("Print Error", f"Failed to generate report: {e}")


def equipment_csv(rows, filepath):
    """materials_report_tab.export_csv (the save-dialog part happens in the window layer)."""
    try:
        with open(filepath, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(["Equipment Type", "Rental Frequency (Bills)", "Total Revenue (Rs.)", "Contribution (%)"])
            for values in rows:
                writer.writerow(values[:4])
        return {"message": f"Data exported successfully to\n{os.path.basename(filepath)}"}
    except Exception as e:
        raise UserError("Export Error", f"Failed to export data: {e}")

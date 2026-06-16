# Implementation Plan: Enhancements and Bug Fixes

This plan outlines the steps to fulfill all the requested UI improvements, new features, and bug fixes for the Rental Billing application.

## User Review Required

> [!IMPORTANT]
> **Material Quantity Tracking (Your Question):**
> You asked how we should handle the quantity of material items in the new tab. 
> **My Proposal:** We will calculate it dynamically by querying the `rental_items` table. Since every rental explicitly saves exactly which items and how many were rented (along with the total price), we can easily group the data by `machine_name`. This will let us show exactly how many times an item was rented out and the total revenue collected for it over any given date range. No extra data structures are needed; we just use the existing reliable rental history.

## Open Questions

> [!WARNING]
> **Dynamic PDF Printing:**
> You requested that in the return processing estimate and tax print, the total amount printed should reflect the **net balance** instead of the static total. 
> *Question:* Do you want the label "Total" on the PDF to remain as "Total" but just show the net balance amount, or do you want the label changed to "Net Balance" when printing from the return processing screen? For now, I will keep the label as "Total" but update the underlying amount to match the net balance.

> [!WARNING]
> **Refund History Storage:**
> Since you requested a `+` button for the refund field and a "Refund/Paid" toggle for the history box, we need a place to save individual refund transactions (with date, amount, and cashier name). 
> *Question:* I plan to create a new database table called `refunds_history` (similar to the `installments` table) to securely track these. Is this acceptable?

## Proposed Changes

---

### UI & Authentication (main.py)

#### [MODIFY] [main.py](file:///f:/Projects/rental/main.py)
- **Authentication**: Add a password prompt popup in the `run()` method before loading the main interface. The application will immediately exit if the user closes the popup or enters an incorrect password. The password will be hardcoded as `MEENA@11`.
- **New Tab Registration**: Register the upcoming `materials_report_tab.py` to the application Notebook.

---

### Return Processing Enhancements

#### [MODIFY] [return_form.py](file:///f:/Projects/rental/return_form.py)
- **Refund Field Update**: Change the `refund` entry to be `readonly` and add a `➕` button next to it.
- **Refund Popup**: Implement an `open_refund_popup` function (analogous to `open_payment_popup`) to prompt for the refund amount and the cashier name.
- **Payment History Toggles**: Add radio buttons ("Refund" and "Paid", with "Refund" selected by default) to the right side of the "Payment History" frame title.
- **History Display Logic**: Link the radio buttons to dynamically switch the contents of the treeview to display either past installments or past refunds.

#### [MODIFY] [db_manager.py](file:///f:/Projects/rental/db_manager.py)
- **New Table**: Create a `refunds_history` table to store `rental_id`, `amount`, `cashier_name`, and `date_time` so that individual refund records can be populated in the history treeview.

#### [MODIFY] [return_logic.py](file:///f:/Projects/rental/return_logic.py)
- **Save Refunds**: Implement `save_refund_history(db, rental_id, amount, cashier_name, date_time)` and a corresponding `get_refunds(db, rental_id)` function.

---

### Dynamic PDF Printing

#### [MODIFY] [return_form.py](file:///f:/Projects/rental/return_form.py)
- **PDF Logic Hook**: In the `on_print_bill` method, update the `total` argument passed to `generate_bill` to use `fields["balance"].get()` rather than the static `due` amount. This ensures the PDF displays the post-deduction/damage net balance.

#### [MODIFY] [billing.py](file:///f:/Projects/rental/billing.py)
- **Label Update (Optional depending on feedback)**: Ensure the layout correctly accommodates the net balance amount without breaking formatting.

---

### Material Analytics Tab

#### [NEW] [materials_report_tab.py](file:///f:/Projects/rental/materials_report_tab.py)
- **New Interface**: Build a tab with a date-range filter.
- **Table Data**: Display columns such as `Machine Name`, `Times Rented (Qty)`, and `Total Revenue Collected`.
- **Query Logic**: Join `rental_items` and `rentals` to aggregate data safely, ensuring cancelled orders aren't counted.

---

### Bug Fixes

#### [MODIFY] [form_logic.py](file:///f:/Projects/rental/form_logic.py)
- **Address Autofill Fix**: In `populate_form_from_record`, the `address_text` widget `.delete()` and `.insert()` operations are silently failing because the widget may be in a `DISABLED` state when a user selects a different row while viewing a record.
- *Fix:* Temporarily set the widget state to `tk.NORMAL`, update the text, and revert the state if necessary.

## Verification Plan

### Manual Verification
1. Launch the app and confirm the `MEENA@11` password prompt prevents access without correct input.
2. Go to the Outward Billing tab, select a row while the form is disabled, and ensure the Address field updates correctly.
3. In Return Processing, add a refund via the `+` button and verify it appears in the history treeview (under the Refund radio button).
4. Print an Estimate/Tax invoice from the Return screen and confirm the total matches the calculated Net Balance.
5. Open the new Materials Details tab and verify historical quantities and revenues load correctly.

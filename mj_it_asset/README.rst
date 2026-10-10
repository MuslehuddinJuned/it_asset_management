=====================
IT Asset Management
=====================

.. |badge1| image:: https://img.shields.io/badge/odoo-17.0-875A7B.svg
    :alt: Odoo 17.0
.. |badge2| image:: https://img.shields.io/badge/licence-LGPL--3-blue.svg
    :target: https://www.gnu.org/licenses/lgpl-3.0-standalone.html
    :alt: License: LGPL-3
.. |badge3| image:: https://img.shields.io/badge/edition-Community%20%26%20Enterprise-success.svg
    :alt: Community & Enterprise

|badge1| |badge2| |badge3|

Register IT equipment by serial number, hand it over to employees with a complete,
auditable history, link every asset to its Purchase Order and let employees and IT
vendors work from the customer portal.

This is a **standalone** IT asset register: it is *not* linked to Odoo Products or to
the Accounting *Assets* (depreciation) app, so it works the same on Community and
Enterprise without any accounting set-up.

**Table of contents**

.. contents::
   :local:

Features
========

Backend
-------

* IT asset register with automatic code (``ITA/00001``), category, brand, model,
  location, specification and photo.
* **Serial number** mandatory and unique per company; searchable everywhere.
* Lifecycle states: *Available*, *Assigned*, *In Repair*, *Lost / Stolen*,
  *Retired / Disposed*.
* **Assign / Re-assign / Return** wizards (also for several assets at once) with date,
  condition (*New, Good, Fair, Damaged*) and notes.
* **Complete assignment history**: when an asset changes hands, the previous holder's
  line is closed with a reason (*Employee Left / Resigned, Re-assigned, Upgrade /
  Replacement, Sent for Repair, Lost / Stolen, Retired / Disposed, Other*). Nothing
  is overwritten; department and job position are kept as they were at the time.
* History lines can be corrected; every change is logged in the chatter.
* Data integrity: one holder at a time, no overlapping assignment periods, no
  duplicate serial numbers.
* **Employee form**: *IT Assets* smart button and tab, with
  *Re-assign All to Another Employee* and *Return All to IT* for leavers.
* **Purchase Orders**: link assets to a PO and PO line (vendor, date and cost are
  filled automatically); *Create IT Assets* on confirmed POs proposes one line per
  ordered unit not yet registered - just type the serial numbers.
* Search filters: warranty expired, held by archived (former) employees, linked to a
  PO; group by status, category, employee, department, PO or vendor.

Portal (``/my/it-assets``)
--------------------------

* **Employees** linked to a portal user (*Related User* or *Work Contact*) see the
  assets assigned to them and their history.
* Portal users flagged as **IT Asset Portal Manager** (e.g. an outsourced IT vendor)
  can add and edit assets, assign, re-assign and return them, change their status,
  manage categories and create assets from confirmed Purchase Orders.
* Search, filters, sorting and **Group By** (Status, Category, Employee, Department,
  Purchase Order, Vendor) on the asset list and on the assignment history.

Installation
============

Copy the ``mj_it_asset`` folder into your addons path (the *parent* folder must be
listed in ``addons_path``), restart Odoo, update the Apps list and install
**IT Asset Management**.

Dependencies: ``hr`` (Employees), ``purchase`` (Purchase), ``portal``, ``mail``.

Configuration
=============

#. Give your IT team the **IT Asset / Manager** access right
   (*Settings > Users*).
#. Create categories in *IT Assets > Configuration > Categories*
   (Laptop, Monitor, Printer, ...).
#. Optional - portal: open a portal user, tab *Access Rights*, and tick
   **IT Asset Portal Manager** to let them manage assets from the portal.
   Employees need no configuration: they are matched through the employee's
   *Related User* or *Work Contact*.

Access rights
-------------

=================================  ==========================================================
Group                              Rights
=================================  ==========================================================
IT Asset / User                    Read-only (backend and portal)
IT Asset / Manager                 Create, edit, assign, re-assign, return, create from PO
Settings / Administration          Everything, including **delete**
IT Asset Portal Manager (portal)   Full asset management from the portal, own companies only
Employees                          Their own assets and history on the portal
=================================  ==========================================================

Usage
=====

#. Register assets manually (*IT Assets > Assets > IT Assets*) or open a confirmed
   Purchase Order and click **Create IT Assets**.
#. Click **Assign** on an available asset and choose the employee.
#. To hand it over (e.g. the employee resigned), click **Re-assign**, choose the new
   employee and the reason for the previous holder.
#. To take it back to IT stock, click **Return** and choose condition, reason and the
   next status.
#. Use *Send to Repair*, *Mark Lost* or *Retire / Dispose* as needed.
#. Review everything in *IT Assets > Assets > Assignment History* or on the employee.

Technical notes
===============

* Developed and tested on Odoo 17.0 (Community & Enterprise).
* Odoo 17 view syntax (``invisible`` / ``readonly`` expressions), classic access rules (``ir.model.access.csv`` + record rules).
* Standalone models: ``it.asset``, ``it.asset.assignment``, ``it.asset.category``; no dependency on Products or Accounting Assets.
* Depends on ``hr``, ``purchase``, ``portal`` and ``mail`` - all available in Odoo Community.
* Portal pages check access explicitly (manager / employee / company) before reading or writing records.
* Automated tests included (backend, access rights and portal).

Credits
=======

Author
------

* Muslehuddin Juned

Contact & support
-----------------

* Email: juned.ipe@gmail.com
* WhatsApp: +880 1819571653

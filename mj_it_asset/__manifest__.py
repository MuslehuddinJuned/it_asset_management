{
    "name": "IT Asset Management",
    "version": "18.0.1.0.0",
    "summary": "Track IT assets by serial number, assign them to employees "
               "with full history and link them to Purchase Orders",
    "description": """
IT Asset Management
===================
* Standalone IT asset register (not linked to Odoo Products or Accounting Assets).
* Unique serial number per company.
* Assign / re-assign / return assets with a full assignment history
  (employee left, transfer, upgrade, repair, lost, ...).
* Link assets to Purchase Orders / PO lines and bulk-create assets
  (one per unit, with serial numbers) directly from a confirmed PO.
* Smart buttons on Employee and Purchase Order.
* Portal (/my/it-assets): employees see their own assets; portal users flagged
  as 'IT Asset Portal Manager' can fully manage assets from the portal.
""",
    "author": "Musleh Uddin Juned",
    "website": "http://www.zachai-bachhai.com",
    "category": "Human Resources",
    "depends": ["base", "mail", "hr", "purchase", "portal"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "wizard/it_asset_assign_wizard_views.xml",
        "wizard/it_asset_return_wizard_views.xml",
        "wizard/it_asset_po_wizard_views.xml",
        "views/it_asset_category_views.xml",
        "views/it_asset_assignment_views.xml",
        "views/it_asset_views.xml",
        "views/hr_employee_views.xml",
        "views/purchase_order_views.xml",
        "views/res_users_views.xml",
        "views/portal_templates.xml",
        "views/menus.xml",
    ],
    "images": ["static/description/banner.png"],
    "support": "juned.ipe@gmail.com",
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}

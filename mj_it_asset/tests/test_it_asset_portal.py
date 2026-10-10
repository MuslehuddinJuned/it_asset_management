from odoo import http
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestItAssetPortal(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        portal = cls.env.ref("base.group_portal")
        cls.category = cls.env["it.asset.category"].create({"name": "Portal Laptop"})

        # Portal manager (toggle on the user form)
        cls.mgr = cls.env["res.users"].create({
            "name": "Portal IT Manager", "login": "it_portal_mgr", "password": "it_portal_mgr",
            "group_ids": [(6, 0, [portal.id])],
        })
        cls.mgr.it_asset_portal_manager = True

        # Portal employee, linked through the employee's work contact
        cls.emp_user = cls.env["res.users"].create({
            "name": "Portal Employee", "login": "it_portal_emp", "password": "it_portal_emp",
            "group_ids": [(6, 0, [portal.id])],
        })
        cls.emp = cls.env["hr.employee"].create({
            "name": "Portal Employee", "work_contact_id": cls.emp_user.partner_id.id})
        cls.other_emp = cls.env["hr.employee"].create({"name": "Someone Else"})

        # Portal user with no link at all
        cls.stranger = cls.env["res.users"].create({
            "name": "Stranger", "login": "it_portal_x", "password": "it_portal_x",
            "group_ids": [(6, 0, [portal.id])],
        })

    def _post(self, url, data):
        data = dict(data, csrf_token=http.Request.csrf_token(self))
        return self.url_open(url, data=data)

    def test_01_toggle(self):
        self.assertTrue(self.mgr.it_asset_portal_manager)
        self.assertTrue(self.mgr.has_group("mj_it_asset.group_it_asset_portal_manager"))
        self.assertTrue(self.mgr.share)

    def test_02_manager_full_flow(self):
        self.authenticate("it_portal_mgr", "it_portal_mgr")
        for url in ["/my", "/my/it-assets", "/my/it-assets/new", "/my/it-assets/history",
                    "/my/it-assets/categories", "/my/it-assets/from-po"]:
            res = self.url_open(url)
            self.assertEqual(res.status_code, 200, url)

        # category + asset creation
        self._post("/my/it-assets/categories", {"name": "Portal Monitor", "code": "MON"})
        self.assertTrue(self.env["it.asset.category"].search([("name", "=", "Portal Monitor")]))
        res = self._post("/my/it-assets/new", {
            "name": "HP EliteBook", "serial_no": "PORTAL-SN-1", "category_id": self.category.id})
        self.assertEqual(res.status_code, 200)
        asset = self.env["it.asset"].search([("serial_no", "=", "PORTAL-SN-1")])
        self.assertTrue(asset)
        self.assertIn(f"/my/it-assets/{asset.id}", res.url)

        # duplicate serial is refused with a message, not a crash
        res = self._post("/my/it-assets/new", {
            "name": "Dup", "serial_no": "PORTAL-SN-1", "category_id": self.category.id})
        self.assertEqual(res.status_code, 200)
        self.assertIn("already used", res.text)
        self.assertEqual(self.env["it.asset"].search_count([("serial_no", "=", "PORTAL-SN-1")]), 1)

        # edit
        self._post(f"/my/it-assets/{asset.id}/edit", {
            "name": "HP EliteBook 840", "serial_no": "PORTAL-SN-1",
            "category_id": self.category.id, "brand": "HP"})
        self.assertEqual(asset.name, "HP EliteBook 840")
        self.assertEqual(asset.brand, "HP")

        # detail page
        res = self.url_open(f"/my/it-assets/{asset.id}")
        self.assertEqual(res.status_code, 200)
        self.assertIn("PORTAL-SN-1", res.text)

        # assign -> re-assign (employee left) -> return
        self._post(f"/my/it-assets/{asset.id}/assign", {"employee_id": self.emp.id, "condition": "new"})
        self.assertEqual(asset.employee_id, self.emp)
        self.assertEqual(asset.assignment_ids.assigned_by, self.mgr)
        self._post(f"/my/it-assets/{asset.id}/assign", {
            "employee_id": self.other_emp.id, "previous_reason": "resign"})
        self.assertEqual(asset.employee_id, self.other_emp)
        self.assertEqual(len(asset.assignment_ids), 2)
        self.assertEqual(asset.assignment_ids.filtered(
            lambda a: a.employee_id == self.emp).return_reason, "resign")
        self._post(f"/my/it-assets/{asset.id}/return", {
            "reason": "upgrade", "condition": "fair", "next_state": "available"})
        self.assertEqual(asset.state, "available")
        self.assertFalse(asset.employee_id)

        # status buttons
        self._post(f"/my/it-assets/{asset.id}/status", {"action": "repair"})
        self.assertEqual(asset.state, "repair")
        # assigning while in repair gives an error message and changes nothing
        res = self._post(f"/my/it-assets/{asset.id}/assign", {"employee_id": self.emp.id})
        self.assertIn("error=", res.url)
        self.assertEqual(asset.state, "repair")
        self._post(f"/my/it-assets/{asset.id}/status", {"action": "available"})
        self.assertEqual(asset.state, "available")

    def test_03_manager_from_po(self):
        vendor = self.env["res.partner"].create({"name": "Portal Vendor"})
        product = self.env["product.product"].create({"name": "Docking Station", "type": "consu"})
        po = self.env["purchase.order"].create({
            "partner_id": vendor.id,
            "order_line": [(0, 0, {"product_id": product.id, "product_qty": 2, "price_unit": 80})],
        })
        po.button_confirm()
        self.authenticate("it_portal_mgr", "it_portal_mgr")
        res = self.url_open(f"/my/it-assets/from-po?po_id={po.id}")
        self.assertEqual(res.status_code, 200)
        self.assertIn("serial_1", res.text)
        line = po.order_line
        res = self._post(f"/my/it-assets/from-po?po_id={po.id}", {
            "default_category_id": self.category.id,
            "line_0": line.id, "include_0": "1", "name_0": "Dock", "serial_0": "DOCK-1", "value_0": "80",
            "line_1": line.id, "include_1": "1", "name_1": "Dock", "serial_1": "DOCK-2", "value_1": "80",
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(po.it_asset_count, 2)
        self.assertEqual(set(po.it_asset_ids.mapped("serial_no")), {"DOCK-1", "DOCK-2"})
        self.assertEqual(po.it_asset_ids[0].vendor_id, vendor)

    def test_04_employee_sees_only_own(self):
        mine = self.env["it.asset"].create({
            "name": "My Laptop", "serial_no": "MINE-1", "category_id": self.category.id})
        other = self.env["it.asset"].create({
            "name": "Not Mine", "serial_no": "OTHER-1", "category_id": self.category.id})
        mine._assign_to_employee(self.emp)
        other._assign_to_employee(self.other_emp)

        self.authenticate("it_portal_emp", "it_portal_emp")
        res = self.url_open("/my/it-assets")
        self.assertIn("MINE-1", res.text)
        self.assertNotIn("OTHER-1", res.text)
        self.assertNotIn("New Asset", res.text)
        res = self.url_open(f"/my/it-assets/{mine.id}")
        self.assertIn("MINE-1", res.text)
        # other asset: redirected back to the list
        res = self.url_open(f"/my/it-assets/{other.id}")
        self.assertNotIn("OTHER-1", res.text)
        # cannot manage
        self.url_open("/my/it-assets/new")
        res = self._post(f"/my/it-assets/{mine.id}/return", {"reason": "other"})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(mine.state, "assigned")
        res = self.url_open("/my/it-assets/history")
        self.assertIn("MINE-1", res.text)
        self.assertNotIn("OTHER-1", res.text)

    def test_05_stranger_no_access(self):
        self.authenticate("it_portal_x", "it_portal_x")
        res = self.url_open("/my/it-assets")
        self.assertTrue(res.url.endswith("/my"))

    def test_06_group_by(self):
        cat2 = self.env["it.asset.category"].create({"name": "Portal Phone"})
        a1 = self.env["it.asset"].create({"name": "GB Laptop", "serial_no": "GB-1", "category_id": self.category.id})
        self.env["it.asset"].create({"name": "GB Phone", "serial_no": "GB-2", "category_id": cat2.id})
        a1._assign_to_employee(self.emp)
        self.authenticate("it_portal_mgr", "it_portal_mgr")
        for gb in ["none", "state", "category", "employee", "department", "purchase_order", "vendor", "bogus"]:
            res = self.url_open(f"/my/it-assets?groupby={gb}")
            self.assertEqual(res.status_code, 200, gb)
        res = self.url_open("/my/it-assets?groupby=category")
        self.assertIn("Portal Phone", res.text)
        self.assertIn("fa-folder-open-o", res.text)
        self.assertIn("Group By", res.text)
        res = self.url_open("/my/it-assets?groupby=state")
        self.assertIn("Assigned", res.text)
        for gb in ["none", "asset", "employee", "department", "category", "reason", "state"]:
            res = self.url_open(f"/my/it-assets/history?groupby={gb}")
            self.assertEqual(res.status_code, 200, gb)
        # employees can group their own list too
        self.authenticate("it_portal_emp", "it_portal_emp")
        res = self.url_open("/my/it-assets?groupby=category")
        self.assertIn("GB-1", res.text)
        self.assertNotIn("GB-2", res.text)

    def test_07_internal_readonly_user_portal(self):
        """Internal IT Asset Users see all assets on the portal but cannot manage."""
        self.env["res.users"].create({
            "name": "IT Reader", "login": "it_reader_p", "password": "it_reader_p",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("mj_it_asset.group_it_asset_user").id])]})
        asset = self.env["it.asset"].create({
            "name": "RO Laptop", "serial_no": "RO-1", "category_id": self.category.id})
        self.authenticate("it_reader_p", "it_reader_p")
        res = self.url_open("/my/it-assets")
        self.assertIn("RO-1", res.text)
        self.assertNotIn("New Asset", res.text)
        res = self._post(f"/my/it-assets/{asset.id}/status", {"action": "repair"})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(asset.state, "available")

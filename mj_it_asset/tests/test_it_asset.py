from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestItAsset(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env["it.asset.category"].create({"name": "Laptop TEST"})
        cls.emp_a = cls.env["hr.employee"].create({"name": "Employee A"})
        cls.emp_b = cls.env["hr.employee"].create({"name": "Employee B"})
        cls.asset = cls.env["it.asset"].create({
            "name": "Dell Latitude", "tag_no": "  TAG-001 ", "serial_no": "  SN-001 ", "category_id": cls.category.id})

    def _assign(self, assets, employee, **kw):
        wiz = Form(self.env["it.asset.assign.wizard"].with_context(
            default_asset_ids=[(6, 0, assets.ids)]))
        wiz.employee_id = employee
        for k, v in kw.items():
            setattr(wiz, k, v)
        wiz.save().action_confirm()

    def test_01_create(self):
        self.assertTrue(self.asset.code.startswith("ITA/"))
        self.assertEqual(self.asset.serial_no, "SN-001")
        self.assertEqual(self.asset.tag_no, "TAG-001")
        self.assertEqual(self.asset.state, "available")
        self.assertIn("Tag: TAG-001", self.asset.display_name)

    def test_02_unique_serial(self):
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.env["it.asset"].create({
                    "name": "Dup", "serial_no": "SN-001", "category_id": self.category.id})

    def test_03_assign_reassign_return(self):
        self._assign(self.asset, self.emp_a)
        self.assertEqual(self.asset.state, "assigned")
        self.assertEqual(self.asset.employee_id, self.emp_a)
        self.assertEqual(self.asset.current_assignment_id.tag_no, "TAG-001")
        self.assertEqual(self.emp_a.it_asset_count, 1)

        # Employee A leaves -> hand over to B, history is kept
        self._assign(self.asset, self.emp_b, previous_reason="resign")
        self.assertEqual(self.asset.employee_id, self.emp_b)
        self.assertEqual(len(self.asset.assignment_ids), 2)
        old = self.asset.assignment_ids.filtered(lambda a: a.employee_id == self.emp_a)
        self.assertEqual(old.state, "returned")
        self.assertEqual(old.return_reason, "resign")
        self.assertTrue(old.date_returned)
        self.assertEqual(self.emp_a.it_asset_count, 0)
        self.assertEqual(len(self.emp_a.it_assignment_ids), 1)

        # Return to IT stock as damaged -> goes to repair
        wiz = Form(self.env["it.asset.return.wizard"].with_context(
            default_asset_ids=[(6, 0, self.asset.ids)]))
        wiz.reason = "upgrade"
        wiz.condition = "damaged"
        self.assertEqual(wiz.next_state, "repair")
        wiz.save().action_confirm()
        self.assertEqual(self.asset.state, "repair")
        self.assertFalse(self.asset.employee_id)
        self.assertTrue(all(a.state == "returned" for a in self.asset.assignment_ids))

        # Cannot assign while in repair
        with self.assertRaises(UserError):
            self.asset._assign_to_employee(self.emp_a)
        self.asset.action_set_available()
        self._assign(self.asset, self.emp_a)
        self.assertEqual(len(self.asset.assignment_ids), 3)

    def test_04_same_employee(self):
        self._assign(self.asset, self.emp_a)
        with self.assertRaises(UserError):
            self.asset._assign_to_employee(self.emp_a)

    def test_05_from_purchase_order(self):
        vendor = self.env["res.partner"].create({"name": "Vendor X"})
        product = self.env["product.product"].create({"name": "Monitor", "type": "consu"})
        po = self.env["purchase.order"].create({
            "partner_id": vendor.id,
            "order_line": [(0, 0, {"product_id": product.id, "product_qty": 3, "price_unit": 150})],
        })
        po.button_confirm()
        wiz_form = Form(self.env["it.asset.po.wizard"].with_context(
            default_purchase_order_id=po.id))
        wiz_form.category_id = self.category
        self.assertEqual(len(wiz_form.line_ids), 3)
        for i in range(3):
            with wiz_form.line_ids.edit(i) as line:
                line.serial_no = f"MON-{i}"
        wiz_form.save().action_confirm()
        self.assertEqual(po.it_asset_count, 3)
        asset = po.it_asset_ids[:1]
        self.assertEqual(asset.vendor_id, vendor)
        self.assertEqual(asset.purchase_value, 150)
        self.assertEqual(asset.purchase_line_id, po.order_line)
        # Nothing left to create for this PO
        wiz2 = Form(self.env["it.asset.po.wizard"].with_context(default_purchase_order_id=po.id))
        self.assertEqual(len(wiz2.line_ids), 0)

    def test_06_po_wizard_duplicate_serial(self):
        vendor = self.env["res.partner"].create({"name": "Vendor Y"})
        po = self.env["purchase.order"].create({
            "partner_id": vendor.id,
            "order_line": [(0, 0, {"name": "Keyboard", "product_qty": 1, "price_unit": 10,
                                   "product_id": self.env["product.product"].create(
                                       {"name": "Keyboard"}).id})],
        })
        wiz = Form(self.env["it.asset.po.wizard"].with_context(default_purchase_order_id=po.id))
        wiz.category_id = self.category
        with wiz.line_ids.edit(0) as line:
            line.serial_no = "SN-001"   # already used
        with self.assertRaises(UserError):
            wiz.save().action_confirm()

    def test_07_lost_closes_assignment(self):
        self._assign(self.asset, self.emp_a)
        self.asset.action_set_lost()
        self.assertEqual(self.asset.state, "lost")
        self.assertEqual(self.asset.assignment_ids.return_reason, "lost")
        self.assertFalse(self.asset.employee_id)

    def test_08_archived_employee_filter(self):
        self._assign(self.asset, self.emp_a)
        self.emp_a.action_archive()
        found = self.env["it.asset"].search([("employee_id.active", "=", False)])
        self.assertIn(self.asset, found)

    def test_09_edit_history_tracked(self):
        self._assign(self.asset, self.emp_a)
        self._assign(self.asset, self.emp_b, previous_reason="resign")
        old = self.asset.assignment_ids.filtered(lambda a: a.employee_id == self.emp_a)
        current = self.asset.current_assignment_id
        # simulate a later transaction (Odoo folds same-transaction changes into creation)
        self.env.flush_all()
        self.env.cr.precommit.run()
        # correct the employee of the current line -> asset holder follows, change is logged
        emp_c = self.env["hr.employee"].create({"name": "Employee C"})
        with Form(current) as f:
            f.employee_id = emp_c
            f.condition_out = "fair"
        self.assertEqual(self.asset.employee_id, emp_c)
        self.env.flush_all()
        self.env.cr.precommit.run()   # tracking values are written at commit time
        self.env.invalidate_all()     # the form view had cached the (empty) chatter
        tracked = current.message_ids.tracking_value_ids.mapped("field_id.name")
        self.assertIn("employee_id", tracked)
        self.assertIn("condition_out", tracked)
        self.assertTrue(any("corrected" in (m.body or "") for m in self.asset.message_ids))
        # edit the old (returned) line too
        old.write({"return_reason": "upgrade", "return_note": "fixed reason"})
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.env.invalidate_all()
        self.assertIn("return_reason", old.message_ids.tracking_value_ids.mapped("field_id.name"))

    def test_10_history_edit_validation(self):
        from odoo.exceptions import ValidationError
        self._assign(self.asset, self.emp_a, date_assigned=fields.Date.to_date("2026-01-01"))
        self._assign(self.asset, self.emp_b, date_assigned=fields.Date.to_date("2026-03-01"))
        old = self.asset.assignment_ids.filtered(lambda a: a.employee_id == self.emp_a)
        with self.assertRaises(ValidationError):   # overlaps with the current holder
            old.date_returned = fields.Date.to_date("2026-04-01")
        with self.assertRaises(ValidationError):   # active line cannot have a return date
            self.asset.current_assignment_id.date_returned = fields.Date.to_date("2026-05-01")
        with self.assertRaises(ValidationError):   # cannot move a line to another asset
            other = self.env["it.asset"].create({
                "name": "X", "serial_no": "X-1", "category_id": self.category.id})
            old.asset_id = other

    def test_11_only_settings_admin_can_delete(self):
        from odoo.exceptions import AccessError
        manager = self.env["res.users"].create({
            "name": "IT Manager", "login": "itmgr_test",
            "groups_id": [(6, 0, [self.env.ref("mj_it_asset.group_it_asset_manager").id])]})
        self.assertFalse(manager.has_group("base.group_system"))
        self._assign(self.asset, self.emp_a)
        for rec in (self.asset, self.asset.assignment_ids, self.category):
            with self.assertRaises(AccessError):
                rec.with_user(manager).unlink()
        # manager can still edit
        self.asset.assignment_ids.with_user(manager).assign_note = "edited by manager"
        # Settings admin can delete; deleting the running line frees the asset
        admin = self.env.ref("base.user_admin")
        self.assertTrue(admin.has_group("base.group_system"))
        self.asset.assignment_ids.with_user(admin).unlink()
        self.assertEqual(self.asset.state, "available")
        self.asset.with_user(admin).unlink()
        self.assertFalse(self.asset.exists())

    def test_12_edit_several_history_lines_at_once(self):
        """Saving several history lines together must be validated on the final
        result, whatever order the lines are written in."""
        from odoo.exceptions import ValidationError
        d = fields.Date.to_date
        self.asset._assign_to_employee(self.emp_a, date=d("2026-10-05"))
        self.asset._assign_to_employee(self.emp_b, date=d("2026-10-05"))
        old = self.asset.assignment_ids.filtered(lambda a: a.employee_id == self.emp_a)
        cur = self.asset.current_assignment_id
        # current line first: on its own it would clash with the not-yet-moved old line
        self.asset.write({"assignment_ids": [
            (1, cur.id, {"date_assigned": d("2026-10-01")}),
            (1, old.id, {"date_assigned": d("2026-09-27"), "date_returned": d("2026-10-01")}),
        ]})
        self.assertEqual((old.date_assigned, old.date_returned), (d("2026-09-27"), d("2026-10-01")))
        self.assertEqual(self.asset.assigned_date, d("2026-10-01"))
        # the user's case: move only the old line back in time
        self.asset.write({"assignment_ids": [
            (1, old.id, {"date_assigned": d("2026-09-20"), "date_returned": d("2026-09-30")})]})
        # a real overlap is still refused, with both periods in the message
        with self.assertRaises(ValidationError) as cm:
            self.asset.write({"assignment_ids": [(1, old.id, {"date_returned": d("2026-10-03")})]})
        self.assertIn("Employee A", str(cm.exception))
        self.assertIn("still in use", str(cm.exception))

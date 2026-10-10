from odoo import _, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    it_asset_ids = fields.One2many(
        "it.asset", "employee_id", string="Current IT Assets",
        groups="mj_it_asset.group_it_asset_user")
    it_assignment_ids = fields.One2many(
        "it.asset.assignment", "employee_id", string="IT Asset History",
        groups="mj_it_asset.group_it_asset_user")
    it_asset_count = fields.Integer(
        compute="_compute_it_asset_count", groups="mj_it_asset.group_it_asset_user")

    def _compute_it_asset_count(self):
        data = self.env["it.asset"]._read_group(
            [("employee_id", "in", self.ids)], ["employee_id"], ["__count"])
        counts = {emp.id: count for emp, count in data}
        for emp in self:
            emp.it_asset_count = counts.get(emp.id, 0)

    def action_view_it_assets(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("mj_it_asset.action_it_asset")
        action["domain"] = [("employee_id", "=", self.id)]
        action["context"] = {"create": False}
        return action

    def action_view_it_asset_history(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "mj_it_asset.action_it_asset_assignment")
        action["domain"] = [("employee_id", "=", self.id)]
        action["context"] = {"create": False}
        return action

    def action_reassign_it_assets(self):
        """Hand over all assets of this employee to someone else (e.g. on leaving)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Re-assign IT Assets of %s", self.name),
            "res_model": "it.asset.assign.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_asset_ids": [(6, 0, self.it_asset_ids.ids)],
                "default_previous_reason": "resign" if not self.active else "transfer",
            },
        }

    def action_return_it_assets(self):
        """Return all assets of this employee to IT stock."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Return IT Assets of %s", self.name),
            "res_model": "it.asset.return.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_asset_ids": [(6, 0, self.it_asset_ids.ids)],
                "default_reason": "resign",
            },
        }

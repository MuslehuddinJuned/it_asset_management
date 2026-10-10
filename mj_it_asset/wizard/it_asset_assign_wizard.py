from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.it_asset_assignment import CONDITIONS, RETURN_REASONS


class ItAssetAssignWizard(models.TransientModel):
    _name = "it.asset.assign.wizard"
    _description = "Assign / Re-assign IT Assets"

    asset_ids = fields.Many2many(
        "it.asset", string="Assets", required=True,
        domain="[('state', 'in', ('available', 'assigned'))]")
    employee_id = fields.Many2one("hr.employee", string="Assign To", required=True)
    date_assigned = fields.Date(required=True, default=fields.Date.context_today)
    condition = fields.Selection(CONDITIONS, string="Condition", default="good", required=True)
    note = fields.Text()
    has_assigned = fields.Boolean(compute="_compute_has_assigned")
    previous_reason = fields.Selection(
        RETURN_REASONS, string="Reason for Leaving Previous Holder", default="transfer",
        help="Recorded on the closed history line of assets that are currently "
             "assigned to someone else.")

    @api.depends("asset_ids")
    def _compute_has_assigned(self):
        for wiz in self:
            wiz.has_assigned = any(a.state == "assigned" for a in wiz.asset_ids)

    def action_confirm(self):
        self.ensure_one()
        if not self.asset_ids:
            raise UserError(_("Select at least one asset."))
        self.asset_ids._assign_to_employee(
            self.employee_id, date=self.date_assigned, condition=self.condition,
            note=self.note, previous_reason=self.previous_reason or "transfer")
        return {"type": "ir.actions.act_window_close"}

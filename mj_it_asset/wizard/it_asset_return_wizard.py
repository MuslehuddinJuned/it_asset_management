from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.it_asset_assignment import CONDITIONS, RETURN_REASONS


class ItAssetReturnWizard(models.TransientModel):
    _name = "it.asset.return.wizard"
    _description = "Return IT Assets"

    asset_ids = fields.Many2many(
        "it.asset", string="Assets", required=True,
        domain="[('state', '=', 'assigned')]")
    date_returned = fields.Date(required=True, default=fields.Date.context_today)
    reason = fields.Selection(
        [r for r in RETURN_REASONS if r[0] != "transfer"],
        required=True, default="other")
    condition = fields.Selection(CONDITIONS, string="Condition", default="good", required=True)
    next_state = fields.Selection(
        [("available", "Available (back to IT stock)"),
         ("repair", "In Repair"),
         ("lost", "Lost / Stolen"),
         ("retired", "Retired / Disposed")],
        string="Asset Status After Return", required=True, default="available")
    note = fields.Text()

    @api.onchange("reason")
    def _onchange_reason(self):
        mapping = {"repair": "repair", "lost": "lost", "retired": "retired"}
        self.next_state = mapping.get(self.reason, "available")

    @api.onchange("condition")
    def _onchange_condition(self):
        if self.condition == "damaged" and self.next_state == "available":
            self.next_state = "repair"

    def action_confirm(self):
        self.ensure_one()
        if not self.asset_ids:
            raise UserError(_("Select at least one asset."))
        self.asset_ids._return_asset(
            date=self.date_returned, reason=self.reason, condition=self.condition,
            note=self.note, next_state=self.next_state)
        return {"type": "ir.actions.act_window_close"}

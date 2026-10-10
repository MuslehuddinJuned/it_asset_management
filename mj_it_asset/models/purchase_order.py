from odoo import _, api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    it_asset_ids = fields.One2many(
        "it.asset", "purchase_order_id", string="IT Assets",
        groups="mj_it_asset.group_it_asset_user")
    it_asset_count = fields.Integer(
        compute="_compute_it_asset_count", groups="mj_it_asset.group_it_asset_user")

    @api.depends("it_asset_ids")
    def _compute_it_asset_count(self):
        data = self.env["it.asset"]._read_group(
            [("purchase_order_id", "in", self.ids)], ["purchase_order_id"], ["__count"])
        counts = {po.id: count for po, count in data}
        for po in self:
            po.it_asset_count = counts.get(po.id, 0)

    def action_view_it_assets(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("mj_it_asset.action_it_asset")
        action["domain"] = [("purchase_order_id", "=", self.id)]
        action["context"] = {
            "default_purchase_order_id": self.id,
            "default_vendor_id": self.partner_id.id,
        }
        return action

    def action_create_it_assets(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Create IT Assets from %s", self.name),
            "res_model": "it.asset.po.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_purchase_order_id": self.id},
        }


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    it_asset_ids = fields.One2many(
        "it.asset", "purchase_line_id", string="IT Assets",
        groups="mj_it_asset.group_it_asset_user")

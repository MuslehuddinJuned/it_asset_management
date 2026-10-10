from odoo import api, fields, models


class ItAssetCategory(models.Model):
    _name = "it.asset.category"
    _description = "IT Asset Category"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char()
    active = fields.Boolean(default=True)
    description = fields.Text()
    asset_ids = fields.One2many("it.asset", "category_id", string="Assets")
    asset_count = fields.Integer(compute="_compute_asset_count")

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Category name must be unique!"),
    ]

    @api.depends("asset_ids")
    def _compute_asset_count(self):
        data = self.env["it.asset"]._read_group(
            [("category_id", "in", self.ids)], ["category_id"], ["__count"])
        counts = {category.id: count for category, count in data}
        for rec in self:
            rec.asset_count = counts.get(rec.id, 0)

    def action_view_assets(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("mj_it_asset.action_it_asset")
        action["domain"] = [("category_id", "=", self.id)]
        action["context"] = {"default_category_id": self.id}
        return action

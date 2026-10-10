from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    it_asset_portal_manager = fields.Boolean(
        string="IT Asset Portal Manager",
        compute="_compute_it_asset_portal_manager",
        inverse="_inverse_it_asset_portal_manager",
        help="Allow this user to fully manage IT assets from the portal (/my/it-assets).")

    @api.depends("groups_id")
    def _compute_it_asset_portal_manager(self):
        group = self.env.ref("mj_it_asset.group_it_asset_portal_manager", raise_if_not_found=False)
        for user in self:
            user.it_asset_portal_manager = bool(group and group in user.groups_id)

    def _inverse_it_asset_portal_manager(self):
        group = self.env.ref("mj_it_asset.group_it_asset_portal_manager")
        for user in self:
            if user.it_asset_portal_manager and group not in user.groups_id:
                user.sudo().write({"groups_id": [(4, group.id)]})
            elif not user.it_asset_portal_manager and group in user.groups_id:
                user.sudo().write({"groups_id": [(3, group.id)]})

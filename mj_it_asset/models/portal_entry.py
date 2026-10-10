from odoo import models


class PortalEntry(models.Model):
    _inherit = "portal.entry"

    def _filter_visible_portal_cards(self):
        """IT Asset managers always see the IT Assets card (even with 0 assets),
        everybody else only when the counter is > 0 (standard behaviour)."""
        visible = super()._filter_visible_portal_cards()
        card = self.env.ref("mj_it_asset.portal_entry_it_assets", raise_if_not_found=False)
        user = self.env.user
        if card and card in self and (
                user.has_group("mj_it_asset.group_it_asset_portal_manager")
                or user.has_group("mj_it_asset.group_it_asset_manager")):
            visible |= card
        return visible

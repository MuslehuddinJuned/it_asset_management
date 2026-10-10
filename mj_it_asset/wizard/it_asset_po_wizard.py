from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ItAssetPoWizard(models.TransientModel):
    _name = "it.asset.po.wizard"
    _description = "Create IT Assets from Purchase Order"

    purchase_order_id = fields.Many2one("purchase.order", required=True, readonly=True)
    category_id = fields.Many2one(
        "it.asset.category", string="Default Category",
        help="Used for lines where no category is set.")
    warranty_expiry = fields.Date(
        string="Default Warranty Expiry", help="Used for lines where no warranty date is set.")
    line_ids = fields.One2many("it.asset.po.wizard.line", "wizard_id", string="Assets to Create")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        po = self.env["purchase.order"].browse(
            res.get("purchase_order_id") or self.env.context.get("active_id"))
        if not po:
            return res
        res["purchase_order_id"] = po.id
        if "line_ids" in fields_list:
            lines = []
            for pol in po.order_line.filtered(
                    lambda l: not l.display_type and l.product_id.type != "service"):
                qty = int(pol.product_qty) - len(pol.it_asset_ids)
                for _i in range(max(qty, 0)):
                    lines.append((0, 0, {
                        "purchase_line_id": pol.id,
                        "name": (pol.name or "").split("\n")[0],
                        "purchase_value": pol.price_unit,
                    }))
            res["line_ids"] = lines
        return res

    def action_confirm(self):
        self.ensure_one()
        po = self.purchase_order_id
        if not self.line_ids:
            raise UserError(_("There is nothing to create."))

        serials = [(l.serial_no or "").strip() for l in self.line_ids]
        if not all(serials):
            raise UserError(_("Please enter a serial number on every line."))
        duplicates = {s for s in serials if serials.count(s) > 1}
        if duplicates:
            raise UserError(_("Duplicate serial numbers: %s", ", ".join(sorted(duplicates))))
        existing = self.env["it.asset"].with_context(active_test=False).search([
            ("serial_no", "in", serials), ("company_id", "=", po.company_id.id)])
        if existing:
            raise UserError(_("These serial numbers already exist: %s",
                              ", ".join(existing.mapped("serial_no"))))

        purchase_date = (po.date_approve or po.date_order)
        vals_list = []
        for line in self.line_ids:
            category = line.category_id or self.category_id
            if not category:
                raise UserError(_("Please set a category for '%s' (or a default category).",
                                  line.name))
            pol = line.purchase_line_id
            value = line.purchase_value
            if pol and pol.currency_id != po.company_id.currency_id:
                value = pol.currency_id._convert(
                    value, po.company_id.currency_id, po.company_id,
                    purchase_date.date() if purchase_date else fields.Date.context_today(self))
            vals_list.append({
                "name": line.name,
                "serial_no": line.serial_no.strip(),
                "category_id": category.id,
                "brand": line.brand,
                "model_no": line.model_no,
                "purchase_order_id": po.id,
                "purchase_line_id": pol.id,
                "vendor_id": po.partner_id.id,
                "purchase_date": purchase_date.date() if purchase_date else False,
                "purchase_value": value,
                "warranty_expiry": line.warranty_expiry or self.warranty_expiry,
                "company_id": po.company_id.id,
            })
        assets = self.env["it.asset"].create(vals_list)
        action = self.env["ir.actions.act_window"]._for_xml_id("mj_it_asset.action_it_asset")
        action["domain"] = [("id", "in", assets.ids)]
        return action


class ItAssetPoWizardLine(models.TransientModel):
    _name = "it.asset.po.wizard.line"
    _description = "Create IT Assets from Purchase Order - Line"

    wizard_id = fields.Many2one("it.asset.po.wizard", required=True, ondelete="cascade")
    purchase_line_id = fields.Many2one("purchase.order.line", string="PO Line")
    name = fields.Char(string="Asset Name", required=True)
    serial_no = fields.Char(string="Serial Number")
    category_id = fields.Many2one("it.asset.category", string="Category")
    brand = fields.Char()
    model_no = fields.Char(string="Model")
    warranty_expiry = fields.Date()
    purchase_value = fields.Float(string="Unit Cost")

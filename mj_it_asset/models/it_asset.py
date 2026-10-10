from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

ASSET_STATES = [
    ("available", "Available"),
    ("assigned", "Assigned"),
    ("repair", "In Repair"),
    ("lost", "Lost / Stolen"),
    ("retired", "Retired / Disposed"),
]


class ItAsset(models.Model):
    _name = "it.asset"
    _description = "IT Asset"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _rec_names_search = ["name", "code", "serial_no"]

    # ------------------------------------------------------------------
    # Identification
    # ------------------------------------------------------------------
    code = fields.Char(
        string="Asset Code", readonly=True, copy=False, index=True,
        default=lambda self: _("New"))
    name = fields.Char(string="Asset Name", required=True, tracking=True)
    serial_no = fields.Char(
        string="Serial Number", required=True, copy=False, index=True, tracking=True)
    category_id = fields.Many2one(
        "it.asset.category", string="Category", required=True, tracking=True)
    brand = fields.Char(tracking=True)
    model_no = fields.Char(string="Model")
    specification = fields.Text()
    image = fields.Image(max_width=512, max_height=512)
    location = fields.Char(tracking=True)
    note = fields.Html(string="Notes")
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")

    # ------------------------------------------------------------------
    # Purchase information
    # ------------------------------------------------------------------
    purchase_order_id = fields.Many2one(
        "purchase.order", string="Purchase Order", tracking=True, index=True,
        domain="[('company_id', 'in', (company_id, False))]")
    purchase_line_id = fields.Many2one(
        "purchase.order.line", string="PO Line", index=True,
        domain="[('order_id', '=', purchase_order_id), ('display_type', '=', False)]")
    vendor_id = fields.Many2one("res.partner", string="Vendor", tracking=True)
    purchase_date = fields.Date(tracking=True)
    purchase_value = fields.Monetary(currency_field="currency_id", tracking=True)
    warranty_expiry = fields.Date(string="Warranty Expiry", tracking=True)
    warranty_expired = fields.Boolean(compute="_compute_warranty_expired")

    # ------------------------------------------------------------------
    # Status & current holder
    # ------------------------------------------------------------------
    state = fields.Selection(
        ASSET_STATES, default="available", required=True, tracking=True,
        copy=False, readonly=True)
    assignment_ids = fields.One2many(
        "it.asset.assignment", "asset_id", string="Assignment History")
    current_assignment_id = fields.Many2one(
        "it.asset.assignment", compute="_compute_current_assignment", store=True)
    employee_id = fields.Many2one(
        "hr.employee", string="Assigned To", compute="_compute_current_assignment",
        store=True, tracking=True, index=True)
    department_id = fields.Many2one(
        "hr.department", string="Department", compute="_compute_current_assignment",
        store=True)
    assigned_date = fields.Date(compute="_compute_current_assignment", store=True)
    assignment_count = fields.Integer(compute="_compute_assignment_count")

    _sql_constraints = [
        ("serial_company_uniq", "unique(serial_no, company_id)",
         "This serial number already exists for another IT asset in this company!"),
    ]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("assignment_ids.state", "assignment_ids.employee_id",
                 "assignment_ids.department_id", "assignment_ids.date_assigned")
    def _compute_current_assignment(self):
        for asset in self:
            current = asset.assignment_ids.filtered(lambda a: a.state == "active")[:1]
            asset.current_assignment_id = current
            asset.employee_id = current.employee_id
            asset.department_id = current.department_id
            asset.assigned_date = current.date_assigned

    @api.depends("assignment_ids")
    def _compute_assignment_count(self):
        for asset in self:
            asset.assignment_count = len(asset.assignment_ids)

    @api.depends("warranty_expiry")
    def _compute_warranty_expired(self):
        today = fields.Date.context_today(self)
        for asset in self:
            asset.warranty_expired = bool(
                asset.warranty_expiry and asset.warranty_expiry < today)

    @api.depends("code", "name", "serial_no")
    def _compute_display_name(self):
        for asset in self:
            code = asset.code if asset.code and asset.code != _("New") else False
            name = f"[{code}] {asset.name}" if code else (asset.name or "")
            if asset.serial_no:
                name = f"{name} (SN: {asset.serial_no})"
            asset.display_name = name

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("serial_no"):
                vals["serial_no"] = vals["serial_no"].strip()
            if not vals.get("code") or vals["code"] == _("New"):
                vals["code"] = self.env["ir.sequence"].next_by_code("it.asset") or _("New")
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("serial_no"):
            vals["serial_no"] = vals["serial_no"].strip()
        if "assignment_ids" in vals:
            # History lines edited from the asset form are saved one by one; validate
            # the overlap only once all of them are written (order-independent).
            res = super(ItAsset, self.with_context(it_asset_defer_overlap=True)).write(vals)
            self._check_assignment_overlap()
            return res
        return super().write(vals)

    def _check_assignment_overlap(self):
        """An asset can be held by only one employee at a time: assignment periods
        [date_assigned, date_returned] must not overlap (touching days are allowed)."""
        in_use = _("still in use")

        def _fmt(d):
            return d.strftime("%d-%b-%Y") if d else in_use
        for asset in self:
            lines = asset.assignment_ids.sorted(
                lambda l: (l.date_assigned, l.date_returned or date.max, l.id))
            for prev, nxt in zip(lines, lines[1:]):
                if not prev.date_returned or prev.date_returned > nxt.date_assigned:
                    raise ValidationError(_(
                        "Assignment periods of %(asset)s overlap:\n"
                        "• %(emp1)s: %(s1)s → %(e1)s\n"
                        "• %(emp2)s: %(s2)s → %(e2)s\n\n"
                        "An asset can only be held by one employee at a time. "
                        "The earlier assignment must be returned on or before the next one starts.",
                        asset=asset.display_name,
                        emp1=prev.employee_id.name, s1=_fmt(prev.date_assigned), e1=_fmt(prev.date_returned),
                        emp2=nxt.employee_id.name, s2=_fmt(nxt.date_assigned), e2=_fmt(nxt.date_returned)))

    def copy(self, default=None):
        default = dict(default or {})
        default.setdefault("serial_no", _("%s (copy)", self.serial_no))
        return super().copy(default)

    @api.ondelete(at_uninstall=False)
    def _unlink_if_not_assigned(self):
        if any(asset.state == "assigned" for asset in self):
            raise UserError(_("You cannot delete an asset that is currently assigned. "
                              "Return it first, or archive it."))

    # ------------------------------------------------------------------
    # Onchanges
    # ------------------------------------------------------------------
    @api.onchange("purchase_order_id")
    def _onchange_purchase_order_id(self):
        po = self.purchase_order_id
        if self.purchase_line_id and self.purchase_line_id.order_id != po:
            self.purchase_line_id = False
        if po:
            self.vendor_id = po.partner_id
            self.purchase_date = (po.date_approve or po.date_order).date() \
                if (po.date_approve or po.date_order) else False

    @api.onchange("purchase_line_id")
    def _onchange_purchase_line_id(self):
        line = self.purchase_line_id
        if line:
            if not self.purchase_order_id:
                self.purchase_order_id = line.order_id
            if not self.name:
                self.name = line.name.split("\n")[0] if line.name else False
            self.purchase_value = line.currency_id._convert(
                line.price_unit, self.currency_id, self.company_id,
                self.purchase_date or fields.Date.context_today(self))

    # ------------------------------------------------------------------
    # Business logic
    # ------------------------------------------------------------------
    def _close_active_assignment(self, date=None, reason="other", condition=False, note=False):
        """Close the running assignment of each asset (if any)."""
        date = date or fields.Date.context_today(self)
        for asset in self:
            current = asset.assignment_ids.filtered(lambda a: a.state == "active")
            if not current:
                continue
            if date < current[0].date_assigned:
                raise UserError(_(
                    "Return date of %(asset)s cannot be before its assignment date (%(date)s).",
                    asset=asset.display_name, date=current[0].date_assigned))
            current.write({
                "state": "returned",
                "date_returned": date,
                "return_reason": reason,
                "condition_in": condition,
                "return_note": note,
                "returned_by": self.env.user.id,
            })

    def _assign_to_employee(self, employee, date=None, condition="good", note=False,
                            previous_reason="transfer"):
        """Assign (or re-assign) assets to an employee, keeping history."""
        date = date or fields.Date.context_today(self)
        Assignment = self.env["it.asset.assignment"]
        for asset in self:
            if asset.state in ("lost", "retired", "repair"):
                raise UserError(_(
                    "Asset %(asset)s is '%(state)s' and cannot be assigned. "
                    "Set it back to Available first.",
                    asset=asset.display_name,
                    state=dict(ASSET_STATES)[asset.state]))
            if asset.employee_id == employee:
                raise UserError(_("Asset %(asset)s is already assigned to %(emp)s.",
                                  asset=asset.display_name, emp=employee.name))
            previous = asset.employee_id
            asset._close_active_assignment(date=date, reason=previous_reason)
            Assignment.create({
                "asset_id": asset.id,
                "employee_id": employee.id,
                "date_assigned": date,
                "condition_out": condition,
                "assign_note": note,
            })
            asset.state = "assigned"
            if previous:
                body = _("Re-assigned from %(old)s to %(new)s.", old=previous.name, new=employee.name)
            else:
                body = _("Assigned to %(new)s.", new=employee.name)
            asset.message_post(body=body)
        return True

    def _return_asset(self, date=None, reason="other", condition="good", note=False,
                      next_state="available"):
        for asset in self:
            if asset.state != "assigned":
                raise UserError(_("Asset %s is not currently assigned.", asset.display_name))
            employee = asset.employee_id
            asset._close_active_assignment(date=date, reason=reason, condition=condition, note=note)
            asset.state = next_state
            asset.message_post(body=_("Returned by %(emp)s.", emp=employee.name))
        return True

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def _wizard_action(self, xmlid, name):
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": xmlid,
            "view_mode": "form",
            "target": "new",
            "context": {"default_asset_ids": [(6, 0, self.ids)]},
        }

    def action_open_assign_wizard(self):
        return self._wizard_action("it.asset.assign.wizard", _("Assign / Re-assign Asset"))

    def action_open_return_wizard(self):
        return self._wizard_action("it.asset.return.wizard", _("Return Asset"))

    def action_set_repair(self):
        for asset in self:
            if asset.state == "assigned":
                asset._close_active_assignment(reason="repair")
        self.write({"state": "repair"})

    def action_set_lost(self):
        for asset in self:
            if asset.state == "assigned":
                asset._close_active_assignment(reason="lost")
        self.write({"state": "lost"})

    def action_retire(self):
        for asset in self:
            if asset.state == "assigned":
                asset._close_active_assignment(reason="retired")
        self.write({"state": "retired"})

    def action_set_available(self):
        if any(asset.state == "assigned" for asset in self):
            raise UserError(_("Use 'Return' for assets that are currently assigned."))
        self.write({"state": "available"})

    def action_view_assignments(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "mj_it_asset.action_it_asset_assignment")
        action["domain"] = [("asset_id", "=", self.id)]
        action["context"] = {"default_asset_id": self.id, "create": False}
        return action

    def action_view_purchase_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "res_id": self.purchase_order_id.id,
            "view_mode": "form",
        }

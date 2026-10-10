from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

CONDITIONS = [
    ("new", "New"),
    ("good", "Good"),
    ("fair", "Fair"),
    ("damaged", "Damaged"),
]

RETURN_REASONS = [
    ("transfer", "Re-assigned to Another Employee"),
    ("resign", "Employee Left / Resigned"),
    ("upgrade", "Upgrade / Replacement"),
    ("repair", "Sent for Repair"),
    ("lost", "Lost / Stolen"),
    ("retired", "Retired / Disposed"),
    ("other", "Other"),
]


class ItAssetAssignment(models.Model):
    _name = "it.asset.assignment"
    _description = "IT Asset Assignment History"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_assigned desc, id desc"

    asset_id = fields.Many2one(
        "it.asset", string="Asset", required=True, ondelete="cascade", index=True)
    serial_no = fields.Char(related="asset_id.serial_no", store=True, string="Serial Number")
    asset_code = fields.Char(related="asset_id.code", store=True, string="Asset Code")
    category_id = fields.Many2one(related="asset_id.category_id", store=True)
    company_id = fields.Many2one(related="asset_id.company_id", store=True)

    employee_id = fields.Many2one("hr.employee", string="Employee", required=True, index=True,
                                  context={"active_test": False}, tracking=True)
    # Snapshots: kept as they were at assignment time, so history stays correct
    # even if the employee later changes department/job.
    department_id = fields.Many2one("hr.department", string="Department", tracking=True)
    job_id = fields.Many2one("hr.job", string="Job Position", tracking=True)

    date_assigned = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    date_returned = fields.Date(tracking=True)
    duration_days = fields.Integer(string="Days Used", compute="_compute_duration")
    assigned_by = fields.Many2one("res.users", default=lambda self: self.env.user, tracking=True)
    returned_by = fields.Many2one("res.users", tracking=True)

    state = fields.Selection(
        [("active", "In Use"), ("returned", "Returned")],
        default="active", required=True, index=True, tracking=True)
    condition_out = fields.Selection(CONDITIONS, string="Condition (Given)", default="good",
                                     tracking=True)
    condition_in = fields.Selection(CONDITIONS, string="Condition (Returned)", tracking=True)
    return_reason = fields.Selection(RETURN_REASONS, tracking=True)
    assign_note = fields.Text(string="Assignment Note", tracking=True)
    return_note = fields.Text(string="Return Note", tracking=True)

    @api.depends("date_assigned", "date_returned")
    def _compute_duration(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.date_assigned:
                rec.duration_days = ((rec.date_returned or today) - rec.date_assigned).days
            else:
                rec.duration_days = 0

    @api.depends("asset_id", "employee_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.asset_id.display_name or ''} → {rec.employee_id.name or ''}"

    @api.model_create_multi
    def create(self, vals_list):
        # Odoo 19: department/job live on hr.version (HR rights needed) -> read the
        # snapshot with sudo; nothing else from HR is exposed.
        Employee = self.env["hr.employee"].sudo()
        for vals in vals_list:
            if vals.get("employee_id"):
                emp = Employee.browse(vals["employee_id"])
                vals.setdefault("department_id", emp.department_id.id)
                vals.setdefault("job_id", emp.job_id.id)
        records = super().create(vals_list)
        if not self.env.context.get("it_asset_defer_overlap"):
            records.asset_id._check_assignment_overlap()
        return records

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        for rec in self:
            emp = rec.employee_id.sudo()
            rec.department_id = emp.department_id
            rec.job_id = emp.job_id

    def write(self, vals):
        if "asset_id" in vals and any(rec.asset_id.id != vals["asset_id"] for rec in self):
            raise ValidationError(_("The asset of an assignment line cannot be changed."))
        if vals.get("employee_id"):
            emp = self.env["hr.employee"].sudo().browse(vals["employee_id"])
            vals.setdefault("department_id", emp.department_id.id)
            vals.setdefault("job_id", emp.job_id.id)
        old_employees = {rec.id: rec.employee_id for rec in self}
        res = super().write(vals)
        if not self.env.context.get("it_asset_defer_overlap") and \
                {"date_assigned", "date_returned", "state"} & set(vals):
            self.asset_id._check_assignment_overlap()
        if "employee_id" in vals:
            for rec in self:
                old = old_employees[rec.id]
                if old != rec.employee_id:
                    rec.asset_id.message_post(body=_(
                        "Assignment history corrected: %(old)s → %(new)s (assigned on %(date)s).",
                        old=old.name, new=rec.employee_id.name, date=rec.date_assigned))
        return res

    def unlink(self):
        # Only Settings > Administration can delete (ACL). Keep the asset consistent
        # when its running assignment is removed.
        assets = self.filtered(lambda r: r.state == "active").asset_id
        res = super().unlink()
        assets.filtered(lambda a: a.state == "assigned" and not a.current_assignment_id).write(
            {"state": "available"})
        return res

    @api.constrains("state", "date_returned")
    def _check_returned_date(self):
        for rec in self:
            if rec.state == "returned" and not rec.date_returned:
                raise ValidationError(_("A returned assignment must have a return date."))
            if rec.state == "active" and rec.date_returned:
                raise ValidationError(_(
                    "An assignment that is still in use cannot have a return date. "
                    "Use the Return button on the asset instead."))

    @api.constrains("asset_id", "state")
    def _check_single_active(self):
        for rec in self.filtered(lambda r: r.state == "active"):
            count = self.search_count([
                ("asset_id", "=", rec.asset_id.id), ("state", "=", "active")])
            if count > 1:
                raise ValidationError(_(
                    "Asset %s already has an active assignment. "
                    "Return it before assigning it again.", rec.asset_id.display_name))

    @api.constrains("date_assigned", "date_returned")
    def _check_dates(self):
        for rec in self:
            if rec.date_returned and rec.date_returned < rec.date_assigned:
                raise ValidationError(_("Return date cannot be earlier than the assignment date."))

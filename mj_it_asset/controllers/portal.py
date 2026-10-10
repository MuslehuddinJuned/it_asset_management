from itertools import groupby as itergroupby
from urllib.parse import urlencode

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

from ..models.it_asset import ASSET_STATES
from ..models.it_asset_assignment import CONDITIONS, RETURN_REASONS

PAGE_SIZE = 20


class ItAssetPortal(CustomerPortal):
    """Portal pages for IT assets.

    * Portal managers (group ``group_it_asset_portal_manager``) and internal IT
      asset users can fully manage assets of their allowed companies.
    * Any other portal user linked to an employee (employee.user_id or
      employee.work_contact_id) can view the assets assigned to them.

    Records are read/written with sudo() *after* these explicit checks, because
    portal users have no ACL on the backend models.
    """

    # ------------------------------------------------------------------
    # Access helpers
    # ------------------------------------------------------------------
    def _it_is_manager(self):
        user = request.env.user
        return (user.has_group("mj_it_asset.group_it_asset_portal_manager")
                or user.has_group("mj_it_asset.group_it_asset_user"))

    def _it_company_ids(self):
        return request.env.user.company_ids.ids

    def _it_my_employees(self):
        user = request.env.user
        return request.env["hr.employee"].sudo().with_context(active_test=False).search([
            "|", ("user_id", "=", user.id), ("work_contact_id", "=", user.partner_id.id)])

    def _it_asset_domain(self):
        """Domain of assets visible to the current user, or None (no access)."""
        if self._it_is_manager():
            return [("company_id", "in", self._it_company_ids())]
        employees = self._it_my_employees()
        if employees:
            return [("employee_id", "in", employees.ids)]
        return None

    def _it_assignment_domain(self):
        if self._it_is_manager():
            return [("company_id", "in", self._it_company_ids())]
        employees = self._it_my_employees()
        if employees:
            return [("employee_id", "in", employees.ids)]
        return None

    def _it_get_asset(self, asset_id):
        domain = self._it_asset_domain()
        if domain is None:
            raise AccessError(_("You have no access to IT assets."))
        asset = request.env["it.asset"].sudo().with_context(active_test=False).search(
            domain + [("id", "=", asset_id)], limit=1)
        if not asset:
            raise AccessError(_("This asset does not exist or you have no access to it."))
        return asset

    def _it_check_manager(self):
        if not self._it_is_manager():
            raise AccessError(_("You are not allowed to manage IT assets."))

    def _it_redirect(self, url, message=None, error=None):
        params = {}
        if message:
            params["message"] = message
        if error:
            params["error"] = error
        return request.redirect(url + ("?" + urlencode(params) if params else ""))

    def _it_group_records(self, records, field_name, domain):
        """Split ``records`` (already ordered by ``field_name``) into
        [(label, total_count, records)] for grouped portal tables.
        ``total_count`` is the size of the whole group, not only this page."""
        if not field_name:
            return [(None, len(records), records)]
        Model = records.env[records._name]
        field = Model._fields[field_name]
        totals = dict(Model._read_group(domain, [field_name], ["__count"]))
        selection = dict(field._description_selection(records.env)) \
            if field.type == "selection" else {}
        groups = []
        for key, recs in itergroupby(records, key=lambda r: r[field_name]):
            recs = Model.concat(*recs)
            if field.type == "selection":
                label = selection.get(key) or _("None")
            else:
                label = key.display_name if key else _("None")
            groups.append((label, totals.get(key, len(recs)), recs))
        return groups

    # Selection data for forms -------------------------------------------
    def _it_employees(self):
        return request.env["hr.employee"].sudo().search(
            [("company_id", "in", self._it_company_ids() + [False])], order="name")

    def _it_categories(self):
        return request.env["it.asset.category"].sudo().search([])

    def _it_purchase_orders(self):
        return request.env["purchase.order"].sudo().search([
            ("company_id", "in", self._it_company_ids()),
            ("state", "in", ("purchase", "done"))], order="date_order desc, id desc", limit=300)

    def _it_vendors(self):
        return request.env["res.partner"].sudo().search(
            [("supplier_rank", ">", 0)], order="name", limit=500)

    def _it_common_values(self, **kw):
        values = self._prepare_portal_layout_values()
        values.update({
            "it_is_manager": self._it_is_manager(),
            "message": kw.get("message"),
            "error": kw.get("error"),
            "asset_states": dict(ASSET_STATES),
            "conditions": CONDITIONS,
            "return_reasons": RETURN_REASONS,
            "today": fields.Date.context_today(request.env.user),
        })
        return values

    # ------------------------------------------------------------------
    # Portal home counter
    # ------------------------------------------------------------------
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "it_asset_count" in counters:
            domain = self._it_asset_domain()
            values["it_asset_count"] = (
                request.env["it.asset"].sudo().search_count(domain) if domain is not None else 0)
        return values

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------
    @http.route(["/my/it-assets", "/my/it-assets/page/<int:page>"],
                type="http", auth="user", website=True)
    def portal_my_it_assets(self, page=1, sortby="newest", filterby="all", search=None,
                            search_in="all", groupby="none", **kw):
        domain = self._it_asset_domain()
        if domain is None:
            return request.redirect("/my")
        Asset = request.env["it.asset"].sudo()

        searchbar_sortings = {
            "newest": {"label": _("Newest"), "order": "id desc"},
            "code": {"label": _("Asset Code"), "order": "code asc"},
            "tag": {"label": _("Tag No."), "order": "tag_no asc, id desc"},
            "name": {"label": _("Name"), "order": "name asc, id desc"},
            "employee": {"label": _("Employee"), "order": "employee_id, id desc"},
        }
        searchbar_filters = {"all": {"label": _("All"), "domain": []}}
        for key, label in ASSET_STATES:
            searchbar_filters[key] = {"label": label, "domain": [("state", "=", key)]}
        searchbar_inputs = {"all": {"input": "all", "label": _("Search in Name / Code / Tag / Serial / Employee")}}
        searchbar_groupby = {
            "none": {"input": "none", "label": _("None"), "field": False},
            "state": {"input": "state", "label": _("Status"), "field": "state"},
            "category": {"input": "category", "label": _("Category"), "field": "category_id"},
            "employee": {"input": "employee", "label": _("Employee"), "field": "employee_id"},
            "department": {"input": "department", "label": _("Department"), "field": "department_id"},
            "purchase_order": {"input": "purchase_order", "label": _("Purchase Order"),
                               "field": "purchase_order_id"},
            "vendor": {"input": "vendor", "label": _("Vendor"), "field": "vendor_id"},
        }
        groupby = groupby if groupby in searchbar_groupby else "none"
        group_field = searchbar_groupby[groupby]["field"]

        sortby = sortby if sortby in searchbar_sortings else "newest"
        filterby = filterby if filterby in searchbar_filters else "all"
        domain = domain + searchbar_filters[filterby]["domain"]
        if search:
            domain += ["|", "|", "|", "|",
                       ("name", "ilike", search), ("code", "ilike", search),
                       ("tag_no", "ilike", search),
                       ("serial_no", "ilike", search), ("employee_id.name", "ilike", search)]

        total = Asset.search_count(domain)
        pager = portal_pager(
            url="/my/it-assets", total=total, page=page, step=PAGE_SIZE,
            url_args={"sortby": sortby, "filterby": filterby, "search": search or "",
                      "groupby": groupby})
        order = searchbar_sortings[sortby]["order"]
        if group_field:
            order = f"{group_field}, {order}"
        assets = Asset.search(domain, order=order, limit=PAGE_SIZE, offset=pager["offset"])

        values = self._it_common_values(**kw)
        values.update({
            "assets": assets,
            "grouped_assets": self._it_group_records(assets, group_field, domain),
            "searchbar_groupby": searchbar_groupby,
            "groupby": groupby,
            "page_name": "it_asset",
            "default_url": "/my/it-assets",
            "pager": pager,
            "searchbar_sortings": searchbar_sortings,
            "searchbar_filters": searchbar_filters,
            "searchbar_inputs": searchbar_inputs,
            "search_in": search_in,
            "search": search,
            "sortby": sortby,
            "filterby": filterby,
        })
        return request.render("mj_it_asset.portal_my_it_assets", values)

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------
    @http.route("/my/it-assets/<int:asset_id>", type="http", auth="user", website=True)
    def portal_my_it_asset(self, asset_id, **kw):
        try:
            asset = self._it_get_asset(asset_id)
        except AccessError:
            return request.redirect("/my/it-assets")
        values = self._it_common_values(**kw)
        values.update({
            "asset": asset,
            "page_name": "it_asset_detail",
            "employees": self._it_employees() if values["it_is_manager"] else [],
        })
        return request.render("mj_it_asset.portal_my_it_asset", values)

    # ------------------------------------------------------------------
    # Create / edit
    # ------------------------------------------------------------------
    def _it_parse_asset_post(self, post):
        def _int(key):
            try:
                return int(post.get(key) or 0) or False
            except ValueError:
                return False

        def _float(key):
            try:
                return float(post.get(key) or 0.0)
            except ValueError:
                return 0.0

        vals = {
            "name": (post.get("name") or "").strip(),
            "tag_no": (post.get("tag_no") or "").strip() or False,
            "serial_no": (post.get("serial_no") or "").strip(),
            "category_id": _int("category_id"),
            "brand": (post.get("brand") or "").strip() or False,
            "model_no": (post.get("model_no") or "").strip() or False,
            "location": (post.get("location") or "").strip() or False,
            "specification": post.get("specification") or False,
            "purchase_order_id": _int("purchase_order_id"),
            "purchase_line_id": _int("purchase_line_id"),
            "vendor_id": _int("vendor_id"),
            "purchase_date": post.get("purchase_date") or False,
            "purchase_value": _float("purchase_value"),
            "warranty_expiry": post.get("warranty_expiry") or False,
        }
        return vals

    def _it_validate_asset_vals(self, vals, asset=None):
        env = request.env
        company_ids = self._it_company_ids()
        if not vals["name"]:
            raise UserError(_("Asset name is required."))
        if not vals["serial_no"]:
            raise UserError(_("Serial number is required."))
        if not vals["category_id"] or not env["it.asset.category"].sudo().browse(
                vals["category_id"]).exists():
            raise UserError(_("Please select a category."))
        company_id = asset.company_id.id if asset else env.user.company_id.id
        dup = env["it.asset"].sudo().with_context(active_test=False).search([
            ("serial_no", "=", vals["serial_no"]), ("company_id", "=", company_id),
            ("id", "!=", asset.id if asset else 0)], limit=1)
        if dup:
            raise UserError(_("Serial number %s is already used by %s.",
                              vals["serial_no"], dup.display_name))
        po = env["purchase.order"].sudo().browse(vals["purchase_order_id"]) \
            if vals["purchase_order_id"] else env["purchase.order"]
        if po and po.company_id.id not in company_ids:
            raise UserError(_("Invalid purchase order."))
        line = env["purchase.order.line"].sudo().browse(vals["purchase_line_id"]) \
            if vals["purchase_line_id"] else env["purchase.order.line"]
        if line and line.order_id != po:
            vals["purchase_line_id"] = False
            line = env["purchase.order.line"]
        if po:
            vals["vendor_id"] = vals["vendor_id"] or po.partner_id.id
            if not vals["purchase_date"]:
                date = po.date_approve or po.date_order
                vals["purchase_date"] = date.date() if date else False
        if line and not vals["purchase_value"]:
            vals["purchase_value"] = line.price_unit
        if not asset:
            vals["company_id"] = company_id
        return vals

    def _it_form_values(self, asset=None, form=None, **kw):
        values = self._it_common_values(**kw)
        pos = self._it_purchase_orders()
        values.update({
            "asset": asset,
            "form": form or {},
            "page_name": "it_asset_form",
            "categories": self._it_categories(),
            "purchase_orders": pos,
            "purchase_lines": pos.order_line.filtered(lambda l: not l.display_type),
            "vendors": self._it_vendors(),
        })
        return values

    @http.route(["/my/it-assets/new", "/my/it-assets/<int:asset_id>/edit"],
                type="http", auth="user", website=True, methods=["GET", "POST"])
    def portal_it_asset_form(self, asset_id=None, **post):
        if not self._it_is_manager():
            return request.redirect("/my/it-assets")
        asset = self._it_get_asset(asset_id) if asset_id else None
        if request.httprequest.method == "POST":
            vals = self._it_parse_asset_post(post)
            try:
                with request.env.cr.savepoint():
                    vals = self._it_validate_asset_vals(vals, asset)
                    if asset:
                        asset.write(vals)
                    else:
                        asset = request.env["it.asset"].sudo().create(vals)
                return self._it_redirect(f"/my/it-assets/{asset.id}", message=_("Asset saved."))
            except (UserError, ValidationError) as e:
                return request.render("mj_it_asset.portal_it_asset_form", self._it_form_values(
                    asset=asset, form=post, error=str(e.args[0] if e.args else e)))
        return request.render("mj_it_asset.portal_it_asset_form", self._it_form_values(asset=asset))

    # ------------------------------------------------------------------
    # Actions: assign / return / status
    # ------------------------------------------------------------------
    @http.route("/my/it-assets/<int:asset_id>/assign", type="http", auth="user",
                website=True, methods=["POST"])
    def portal_it_asset_assign(self, asset_id, **post):
        self._it_check_manager()
        asset = self._it_get_asset(asset_id)
        url = f"/my/it-assets/{asset.id}"
        employee = request.env["hr.employee"].sudo().browse(int(post.get("employee_id") or 0))
        if not employee.exists() or employee not in self._it_employees():
            return self._it_redirect(url, error=_("Please select a valid employee."))
        try:
            with request.env.cr.savepoint():
                asset._assign_to_employee(
                    employee,
                    date=fields.Date.to_date(post.get("date")) or fields.Date.context_today(asset),
                    condition=post.get("condition") or "good",
                    note=post.get("note") or False,
                    previous_reason=post.get("previous_reason") or "transfer")
        except (UserError, ValidationError) as e:
            return self._it_redirect(url, error=str(e.args[0] if e.args else e))
        return self._it_redirect(url, message=_("Asset assigned to %s.", employee.name))

    @http.route("/my/it-assets/<int:asset_id>/return", type="http", auth="user",
                website=True, methods=["POST"])
    def portal_it_asset_return(self, asset_id, **post):
        self._it_check_manager()
        asset = self._it_get_asset(asset_id)
        url = f"/my/it-assets/{asset.id}"
        next_state = post.get("next_state") or "available"
        if next_state not in ("available", "repair", "lost", "retired"):
            next_state = "available"
        try:
            with request.env.cr.savepoint():
                asset._return_asset(
                    date=fields.Date.to_date(post.get("date")) or fields.Date.context_today(asset),
                    reason=post.get("reason") or "other",
                    condition=post.get("condition") or "good",
                    note=post.get("note") or False,
                    next_state=next_state)
        except (UserError, ValidationError) as e:
            return self._it_redirect(url, error=str(e.args[0] if e.args else e))
        return self._it_redirect(url, message=_("Asset returned."))

    @http.route("/my/it-assets/<int:asset_id>/status", type="http", auth="user",
                website=True, methods=["POST"])
    def portal_it_asset_status(self, asset_id, action=None, **post):
        self._it_check_manager()
        asset = self._it_get_asset(asset_id)
        url = f"/my/it-assets/{asset.id}"
        methods = {
            "repair": asset.action_set_repair,
            "lost": asset.action_set_lost,
            "retire": asset.action_retire,
            "available": asset.action_set_available,
        }
        if action not in methods:
            return self._it_redirect(url, error=_("Unknown action."))
        try:
            with request.env.cr.savepoint():
                methods[action]()
        except (UserError, ValidationError) as e:
            return self._it_redirect(url, error=str(e.args[0] if e.args else e))
        return self._it_redirect(url, message=_("Status updated."))

    # ------------------------------------------------------------------
    # Assignment history
    # ------------------------------------------------------------------
    @http.route(["/my/it-assets/history", "/my/it-assets/history/page/<int:page>"],
                type="http", auth="user", website=True)
    def portal_it_asset_history(self, page=1, search=None, search_in="all", filterby="all",
                                groupby="none", **kw):
        domain = self._it_assignment_domain()
        if domain is None:
            return request.redirect("/my")
        Assignment = request.env["it.asset.assignment"].sudo()
        searchbar_filters = {
            "all": {"label": _("All"), "domain": []},
            "active": {"label": _("In Use"), "domain": [("state", "=", "active")]},
            "returned": {"label": _("Returned"), "domain": [("state", "=", "returned")]},
        }
        searchbar_groupby = {
            "none": {"input": "none", "label": _("None"), "field": False},
            "asset": {"input": "asset", "label": _("Asset"), "field": "asset_id"},
            "employee": {"input": "employee", "label": _("Employee"), "field": "employee_id"},
            "department": {"input": "department", "label": _("Department"), "field": "department_id"},
            "category": {"input": "category", "label": _("Category"), "field": "category_id"},
            "reason": {"input": "reason", "label": _("Return Reason"), "field": "return_reason"},
            "state": {"input": "state", "label": _("Status"), "field": "state"},
        }
        groupby = groupby if groupby in searchbar_groupby else "none"
        group_field = searchbar_groupby[groupby]["field"]
        filterby = filterby if filterby in searchbar_filters else "all"
        domain = domain + searchbar_filters[filterby]["domain"]
        if search:
            domain += ["|", "|", "|", "|",
                       ("asset_id.name", "ilike", search), ("asset_code", "ilike", search),
                       ("tag_no", "ilike", search),
                       ("serial_no", "ilike", search), ("employee_id.name", "ilike", search)]
        total = Assignment.search_count(domain)
        pager = portal_pager(url="/my/it-assets/history", total=total, page=page, step=PAGE_SIZE,
                             url_args={"search": search or "", "filterby": filterby,
                                       "groupby": groupby})
        order = f"{group_field}, date_assigned desc, id desc" if group_field else None
        lines = Assignment.search(domain, order=order, limit=PAGE_SIZE, offset=pager["offset"])
        values = self._it_common_values(**kw)
        values.update({
            "lines": lines,
            "grouped_lines": self._it_group_records(lines, group_field, domain),
            "searchbar_groupby": searchbar_groupby,
            "groupby": groupby,
            "page_name": "it_asset_history",
            "default_url": "/my/it-assets/history",
            "pager": pager,
            "searchbar_filters": searchbar_filters,
            "searchbar_inputs": {"all": {"input": "all", "label": _("Search")}},
            "search_in": search_in,
            "search": search,
            "filterby": filterby,
        })
        return request.render("mj_it_asset.portal_it_asset_history", values)

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------
    @http.route("/my/it-assets/categories", type="http", auth="user", website=True,
                methods=["GET", "POST"])
    def portal_it_asset_categories(self, **post):
        if not self._it_is_manager():
            return request.redirect("/my/it-assets")
        if request.httprequest.method == "POST":
            name = (post.get("name") or "").strip()
            if not name:
                return self._it_redirect("/my/it-assets/categories", error=_("Name is required."))
            Category = request.env["it.asset.category"].sudo().with_context(active_test=False)
            if Category.search_count([("name", "=ilike", name)]):
                return self._it_redirect("/my/it-assets/categories",
                                         error=_("Category %s already exists.", name))
            Category.create({"name": name, "code": (post.get("code") or "").strip() or False})
            return self._it_redirect("/my/it-assets/categories", message=_("Category created."))
        values = self._it_common_values(**post)
        values.update({"categories": self._it_categories(), "page_name": "it_asset_categories"})
        return request.render("mj_it_asset.portal_it_asset_categories", values)

    # ------------------------------------------------------------------
    # Create assets from a Purchase Order
    # ------------------------------------------------------------------
    @http.route("/my/it-assets/from-po", type="http", auth="user", website=True,
                methods=["GET", "POST"])
    def portal_it_asset_from_po(self, po_id=None, **post):
        if not self._it_is_manager():
            return request.redirect("/my/it-assets")
        pos = self._it_purchase_orders()
        po = pos.filtered(lambda p: p.id == int(po_id)) if po_id and str(po_id).isdigit() else \
            request.env["purchase.order"]

        if request.httprequest.method == "POST" and po:
            Wizard = request.env["it.asset.po.wizard"].sudo()
            lines = []
            i = 0
            while f"line_{i}" in post:
                if post.get(f"include_{i}"):
                    lines.append((0, 0, {
                        "purchase_line_id": int(post[f"line_{i}"]) or False,
                        "name": (post.get(f"name_{i}") or "").strip() or _("IT Asset"),
                        "tag_no": (post.get(f"tag_{i}") or "").strip() or False,
                        "serial_no": (post.get(f"serial_{i}") or "").strip(),
                        "category_id": int(post.get(f"category_{i}") or 0) or False,
                        "brand": post.get(f"brand_{i}") or False,
                        "model_no": post.get(f"model_{i}") or False,
                        "warranty_expiry": post.get(f"warranty_{i}") or False,
                        "purchase_value": float(post.get(f"value_{i}") or 0.0),
                    }))
                i += 1
            try:
                with request.env.cr.savepoint():
                    wizard = Wizard.create({
                        "purchase_order_id": po.id,
                        "category_id": int(post.get("default_category_id") or 0) or False,
                        "warranty_expiry": post.get("default_warranty") or False,
                        "line_ids": lines,
                    })
                    wizard.action_confirm()
            except (UserError, ValidationError) as e:
                values = self._it_po_values(po, pos, post=post,
                                            error=str(e.args[0] if e.args else e))
                return request.render("mj_it_asset.portal_it_asset_from_po", values)
            return self._it_redirect(
                "/my/it-assets", message=_("%s asset(s) created from %s.", len(lines), po.name))

        return request.render("mj_it_asset.portal_it_asset_from_po",
                              self._it_po_values(po, pos, **post))

    def _it_po_values(self, po, pos, post=None, **kw):
        values = self._it_common_values(**kw)
        rows = []
        if po:
            defaults = request.env["it.asset.po.wizard"].sudo().with_context(
                default_purchase_order_id=po.id).default_get(["purchase_order_id", "line_ids"])
            PoLine = request.env["purchase.order.line"].sudo()
            for cmd in defaults.get("line_ids", []):
                row = dict(cmd[2])
                pol = PoLine.browse(row["purchase_line_id"])
                row["po_line_label"] = (pol.product_id.display_name or pol.name or "").split("\n")[0]
                rows.append(row)
        values.update({
            "po": po,
            "purchase_orders": pos,
            "rows": rows,
            "post": post or {},
            "categories": self._it_categories(),
            "page_name": "it_asset_po",
        })
        return values

"""
routes/channel_partners.py - Channel partner management
"""
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from ..database import close_db, get_db
from .auth import login_required, role_required
from .channel_partner_helpers import (
    parse_channel_partner_search,
    apply_channel_partner_search,
    build_channel_partner_scope,
    validate_channel_partner_form,
    render_channel_partner_form,
    fetch_channel_partner,
    load_trainers,
)


cp_bp = Blueprint("channel_partners", __name__, url_prefix="/channel-partners")


@cp_bp.route("/")
@login_required
def index():
    search = parse_channel_partner_search(request.args)
    role = session.get("role")
    assigned_loc_id = session.get("location_id")
    conn = get_db(); cur = conn.cursor()
    query, params = build_channel_partner_scope(role, assigned_loc_id)
    query, params = apply_channel_partner_search(query, params, search)
    cur.execute(query + " ORDER BY created_at DESC, name;", params)
    partners = cur.fetchall(); close_db(conn, commit=False)
    return render_template("channel_partners/index.html", partners=partners, search=search)


@cp_bp.route("/add", methods=["GET", "POST"])
@login_required
@role_required("admin", "developer")
def add():
    conn = get_db(); cur = conn.cursor()
    trainers = load_trainers(cur)
    close_db(conn, commit=False)
    if request.method == "POST":
        try:
            cleaned = validate_channel_partner_form(request.form)
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT INTO channel_partners (name,phone,address,email,trainer_id) VALUES (%s,%s,%s,%s,%s);",
                        (cleaned["name"], cleaned.get("phone"), cleaned.get("address"), cleaned.get("email"), cleaned.get("trainer_id")))
            close_db(conn)
            flash("Channel partner created.", "success")
            return redirect(url_for("channel_partners.index"))
        except ValueError as exc:
            close_db(conn, commit=False)
            flash(str(exc), "danger")
            return render_channel_partner_form(partner=None, trainers=trainers, action="Add", form_data=request.form.to_dict(flat=True), form_error_popup=str(exc))
        except Exception:
            current_app.logger.exception("Failed to create channel partner")
            close_db(conn, commit=False)
            flash("Unable to create channel partner right now.", "danger")
            return render_channel_partner_form(partner=None, trainers=trainers, action="Add", form_data=request.form.to_dict(flat=True), form_error_popup=None)
    return render_channel_partner_form(partner=None, trainers=trainers, action="Add")


@cp_bp.route("/<int:cp_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "developer")
def edit(cp_id):
    conn = get_db(); cur = conn.cursor()
    partner = fetch_channel_partner(cur, cp_id)
    trainers = load_trainers(cur)
    close_db(conn, commit=False)
    if not partner:
        flash("Not found.", "danger"); return redirect(url_for("channel_partners.index"))
    if request.method == "POST":
        try:
            cleaned = validate_channel_partner_form(request.form)
            conn = get_db(); cur = conn.cursor()
            cur.execute("UPDATE channel_partners SET name=%s,phone=%s,address=%s,email=%s,trainer_id=%s WHERE id=%s;",
                        (cleaned["name"], cleaned.get("phone"), cleaned.get("address"), cleaned.get("email"), cleaned.get("trainer_id"), cp_id))
            close_db(conn)
            flash("Updated.", "success")
            return redirect(url_for("channel_partners.index"))
        except ValueError as exc:
            close_db(conn, commit=False)
            flash(str(exc), "danger")
            return render_channel_partner_form(partner=partner, trainers=trainers, action="Edit", form_data=request.form.to_dict(flat=True), form_error_popup=str(exc))
        except Exception:
            current_app.logger.exception("Failed to update channel partner %s", cp_id)
            close_db(conn, commit=False)
            flash("Unable to update right now.", "danger")
            return render_channel_partner_form(partner=partner, trainers=trainers, action="Edit", form_data=request.form.to_dict(flat=True), form_error_popup=None)
    return render_channel_partner_form(partner=partner, trainers=trainers, action="Edit")


@cp_bp.route("/<int:cp_id>/delete", methods=["POST"])
@login_required
@role_required("admin", "developer")
def delete(cp_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM channel_partners WHERE id=%s;", (cp_id,))
    close_db(conn)
    flash("Deleted.", "success")
    return redirect(url_for("channel_partners.index"))

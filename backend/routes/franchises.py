"""
routes/franchises.py - Franchise management and sales executives
"""
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for, jsonify

from ..database import close_db, get_db
from .auth import login_required, role_required
from .franchise_helpers import (
    parse_franchise_search,
    apply_franchise_search,
    build_franchise_scope,
    validate_franchise_form,
    render_franchise_form,
    fetch_franchise,
    load_franchise_sales_execs,
    validate_sales_exec_form,
    render_sales_exec_form,
    fetch_sales_exec,
)


franchises_bp = Blueprint("franchises", __name__, url_prefix="/franchises")


@franchises_bp.route("/")
@login_required
def index():
    search = parse_franchise_search(request.args)
    role = session.get("role")
    assigned_loc_id = session.get("location_id")
    conn = get_db(); cur = conn.cursor()
    query, params = build_franchise_scope(role, assigned_loc_id)
    query, params = apply_franchise_search(query, params, search)
    cur.execute(query + " ORDER BY created_at DESC, name;", params)
    franchises = cur.fetchall(); close_db(conn, commit=False)
    return render_template("franchises/index.html", franchises=franchises, search=search)


@franchises_bp.route("/add", methods=["GET", "POST"])
@login_required
@role_required("admin", "developer")
def add():
    if request.method == "POST":
        conn = None
        try:
            cleaned = validate_franchise_form(request.form)
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT INTO franchises (code,name,phone,address) VALUES (%s,%s,%s,%s);",
                        (cleaned["code"], cleaned["name"], cleaned["phone"], cleaned["address"]))
            close_db(conn)
            flash(f"Franchise '{cleaned['name']}' created.", "success")
            return redirect(url_for("franchises.index"))
        except ValueError as exc:
            if conn:
                close_db(conn, commit=False)
            flash(str(exc), "danger")
            return render_franchise_form(franchise=None, action="Add", form_data=request.form.to_dict(flat=True), form_error_popup=str(exc))
        except Exception:
            current_app.logger.exception("Failed to create franchise")
            if conn:
                close_db(conn, commit=False)
            message = "Unable to create the franchise right now."
            flash(message, "danger")
            return render_franchise_form(franchise=None, action="Add", form_data=request.form.to_dict(flat=True), form_error_popup=message)
    return render_franchise_form(franchise=None, action="Add")


@franchises_bp.route("/<int:fr_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "developer")
def edit(fr_id):
    conn = get_db(); cur = conn.cursor()
    franchise = fetch_franchise(cur, fr_id)
    close_db(conn, commit=False)
    if not franchise:
        flash("Not found.", "danger")
        return redirect(url_for("franchises.index"))
    if request.method == "POST":
        try:
            cleaned = validate_franchise_form(request.form)
            conn = get_db(); cur = conn.cursor()
            cur.execute("UPDATE franchises SET code=%s,name=%s,phone=%s,address=%s WHERE id=%s;",
                        (cleaned["code"], cleaned["name"], cleaned["phone"], cleaned["address"], fr_id))
            close_db(conn)
            flash("Updated.", "success")
            return redirect(url_for("franchises.index"))
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_franchise_form(franchise=franchise, action="Edit", form_data=request.form.to_dict(flat=True), form_error_popup=str(exc))
        except Exception:
            current_app.logger.exception("Failed to update franchise %s", fr_id)
            close_db(conn, commit=False)
            message = "Unable to update the franchise right now."
            flash(message, "danger")
            return render_franchise_form(franchise=franchise, action="Edit", form_data=request.form.to_dict(flat=True), form_error_popup=message)
    return render_franchise_form(franchise=franchise, action="Edit")


@franchises_bp.route("/<int:fr_id>/delete", methods=["POST"])
@login_required
@role_required("admin", "developer")
def delete(fr_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM franchises WHERE id=%s;", (fr_id,))
    close_db(conn)
    flash("Deleted.", "success")
    return redirect(url_for("franchises.index"))


@franchises_bp.route("/<int:fr_id>")
@login_required
def detail(fr_id):
    conn = get_db(); cur = conn.cursor()
    franchise = fetch_franchise(cur, fr_id)
    if not franchise:
        close_db(conn, commit=False); flash("Not found.", "danger"); return redirect(url_for("franchises.index"))
    sales_execs = load_franchise_sales_execs(cur, fr_id)
    close_db(conn, commit=False)
    return render_template("franchises/detail.html", franchise=franchise, sales_execs=sales_execs)


# Sales executives CRUD under a franchise
@franchises_bp.route("/<int:fr_id>/sales-execs/add", methods=["GET", "POST"])
@login_required
@role_required("admin", "developer")
def add_sales_exec(fr_id):
    conn = get_db(); cur = conn.cursor()
    franchise = fetch_franchise(cur, fr_id)
    if not franchise:
        close_db(conn,commit=False); flash("Not found.", "danger"); return redirect(url_for("franchises.index"))
    close_db(conn, commit=False)
    if request.method == "POST":
        try:
            cleaned = validate_sales_exec_form(request.form)
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT INTO sales_executives (franchise_id,name,phone,address,email,remarks) VALUES (%s,%s,%s,%s,%s,%s);",
                        (fr_id, cleaned["name"], cleaned["phone"], cleaned["address"], cleaned.get("email"), cleaned.get("remarks")))
            close_db(conn)
            flash("Sales executive added.", "success")
            return redirect(url_for("franchises.detail", fr_id=fr_id))
        except ValueError as exc:
            if conn: close_db(conn,commit=False)
            flash(str(exc), "danger")
            return render_sales_exec_form(franchise=franchise, action="Add", form_data=request.form.to_dict(flat=True), form_error_popup=str(exc))
        except Exception:
            current_app.logger.exception("Failed to add sales exec")
            if conn: close_db(conn,commit=False)
            flash("Unable to add sales executive right now.", "danger")
            return render_sales_exec_form(franchise=franchise, action="Add", form_data=request.form.to_dict(flat=True), form_error_popup=None)
    return render_sales_exec_form(franchise=franchise, action="Add")


@franchises_bp.route("/<int:fr_id>/sales-execs/<int:se_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "developer")
def edit_sales_exec(fr_id, se_id):
    conn = get_db(); cur = conn.cursor()
    franchise = fetch_franchise(cur, fr_id)
    sales_exec = fetch_sales_exec(cur, se_id)
    close_db(conn, commit=False)
    if not franchise or not sales_exec:
        flash("Not found.", "danger"); return redirect(url_for("franchises.index"))
    if request.method == "POST":
        try:
            cleaned = validate_sales_exec_form(request.form)
            conn = get_db(); cur = conn.cursor()
            cur.execute("UPDATE sales_executives SET name=%s,phone=%s,address=%s,email=%s,remarks=%s WHERE id=%s AND franchise_id=%s;",
                        (cleaned["name"], cleaned["phone"], cleaned["address"], cleaned.get("email"), cleaned.get("remarks"), se_id, fr_id))
            close_db(conn)
            flash("Updated.", "success")
            return redirect(url_for("franchises.detail", fr_id=fr_id))
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_sales_exec_form(franchise=franchise, action="Edit", sales_exec=sales_exec, form_data=request.form.to_dict(flat=True), form_error_popup=str(exc))
        except Exception:
            current_app.logger.exception("Failed to update sales exec %s", se_id)
            close_db(conn, commit=False)
            flash("Unable to update right now.", "danger")
            return render_sales_exec_form(franchise=franchise, action="Edit", sales_exec=sales_exec, form_data=request.form.to_dict(flat=True), form_error_popup=None)
    return render_sales_exec_form(franchise=franchise, action="Edit", sales_exec=sales_exec)


@franchises_bp.route("/<int:fr_id>/sales-execs/<int:se_id>/delete", methods=["POST"])
@login_required
@role_required("admin", "developer")
def delete_sales_exec(fr_id, se_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM sales_executives WHERE id=%s AND franchise_id=%s;", (se_id, fr_id))
    close_db(conn)
    flash("Deleted.", "success")
    return redirect(url_for("franchises.detail", fr_id=fr_id))

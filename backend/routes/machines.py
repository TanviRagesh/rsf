"""
routes/machines.py - Machine management with center-aware analytics
"""
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from ..database import close_db, get_db
from .auth import login_required, role_required
from .machine_helpers import (
    apply_machine_search,
    build_machine_scope,
    fetch_machine,
    load_machine_centers,
    parse_machine_search,
    render_machine_form,
    validate_machine_form,
)


machines_bp = Blueprint("machines", __name__, url_prefix="/machines")


@machines_bp.route("/")
@login_required
def index():
    search = parse_machine_search(request.args)
    role = session.get("role")
    assigned_loc_id = session.get("location_id")
    conn = get_db()
    cur = conn.cursor()
    query, params = build_machine_scope(role, assigned_loc_id)
    query, params = apply_machine_search(query, params, search)
    cur.execute(query + " ORDER BY m.created_at DESC, m.machine_name;", params)
    machines = cur.fetchall()
    close_db(conn, commit=False)
    return render_template("machines/index.html", machines=machines, search=search)


@machines_bp.route("/add", methods=["GET", "POST"])
@login_required
@role_required("admin", "developer")
def add():
    role = session.get("role")
    assigned_loc_id = session.get("location_id")
    conn = get_db()
    cur = conn.cursor()
    centers = load_machine_centers(cur, role, assigned_loc_id)
    close_db(conn, commit=False)

    if request.method == "POST":
        write_conn = None
        try:
            cleaned = validate_machine_form(request.form)
            write_conn = get_db()
            cur = write_conn.cursor()
            cur.execute(
                """
                INSERT INTO machines (
                    center_id, machine_name, machine_type, machine_number,
                    capacity, fuel_type, status, remarks
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s);
                """,
                (
                    cleaned["center_id"],
                    cleaned["machine_name"],
                    cleaned["machine_type"],
                    cleaned["machine_number"],
                    cleaned["capacity"],
                    cleaned["fuel_type"],
                    cleaned["status"],
                    cleaned["remarks"],
                ),
            )
            close_db(write_conn)
            flash(f"Machine '{cleaned['machine_name']}' created.", "success")
            return redirect(url_for("machines.index"))
        except ValueError as exc:
            if write_conn:
                close_db(write_conn, commit=False)
            flash(str(exc), "danger")
            return render_machine_form(
                machine=None,
                centers=centers,
                action="Add",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=str(exc),
            )
        except Exception:
            current_app.logger.exception("Failed to create machine")
            if write_conn:
                close_db(write_conn, commit=False)
            message = "Unable to create the machine right now."
            flash(message, "danger")
            return render_machine_form(
                machine=None,
                centers=centers,
                action="Add",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=message,
            )

    return render_machine_form(machine=None, centers=centers, action="Add")


@machines_bp.route("/<int:machine_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "developer")
def edit(machine_id):
    role = session.get("role")
    assigned_loc_id = session.get("location_id")
    conn = get_db()
    cur = conn.cursor()
    machine = fetch_machine(cur, machine_id)
    centers = load_machine_centers(cur, role, assigned_loc_id)
    close_db(conn, commit=False)
    if not machine:
        flash("Not found.", "danger")
        return redirect(url_for("machines.index"))

    if request.method == "POST":
        write_conn = None
        try:
            cleaned = validate_machine_form(request.form)
            write_conn = get_db()
            cur = write_conn.cursor()
            cur.execute(
                """
                UPDATE machines
                SET center_id=%s, machine_name=%s, machine_type=%s, machine_number=%s,
                    capacity=%s, fuel_type=%s, status=%s, remarks=%s
                WHERE id=%s;
                """,
                (
                    cleaned["center_id"],
                    cleaned["machine_name"],
                    cleaned["machine_type"],
                    cleaned["machine_number"],
                    cleaned["capacity"],
                    cleaned["fuel_type"],
                    cleaned["status"],
                    cleaned["remarks"],
                    machine_id,
                ),
            )
            close_db(write_conn)
            flash("Updated.", "success")
            return redirect(url_for("machines.index"))
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_machine_form(
                machine=machine,
                centers=centers,
                action="Edit",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=str(exc),
            )
        except Exception:
            current_app.logger.exception("Failed to update machine %s", machine_id)
            if write_conn:
                close_db(write_conn, commit=False)
            message = "Unable to update the machine right now."
            flash(message, "danger")
            return render_machine_form(
                machine=machine,
                centers=centers,
                action="Edit",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=message,
            )

    return render_machine_form(machine=machine, centers=centers, action="Edit")


@machines_bp.route("/<int:machine_id>/delete", methods=["POST"])
@login_required
@role_required("admin", "developer")
def delete(machine_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE machines SET is_deleted=TRUE WHERE id=%s;", (machine_id,))
    close_db(conn)
    flash("Deleted.", "success")
    return redirect(url_for("machines.index"))


@machines_bp.route("/<int:machine_id>/analytics")
@login_required
def analytics(machine_id):
    role = session.get("role")
    assigned_loc_id = session.get("location_id")
    conn = get_db()
    cur = conn.cursor()

    machine = fetch_machine(cur, machine_id, role=role, assigned_loc_id=assigned_loc_id)
    if not machine:
        close_db(conn, commit=False)
        flash("Not found.", "danger")
        return redirect(url_for("machines.index"))

    if machine["center_id"] is None:
        fleet_where = "m.is_deleted=FALSE AND m.center_id IS NULL"
        fleet_params = []
    else:
        fleet_where = "m.is_deleted=FALSE AND m.center_id=%s"
        fleet_params = [machine["center_id"]]

    cur.execute(
        f"""
        SELECT COUNT(*) AS total_center_machines,
               SUM(CASE WHEN status='AVAILABLE' THEN 1 ELSE 0 END) AS available_machines,
               SUM(CASE WHEN machine_type=%s THEN 1 ELSE 0 END) AS same_type_machines,
               SUM(CASE WHEN fuel_type=%s THEN 1 ELSE 0 END) AS same_fuel_machines
        FROM machines m
        WHERE {fleet_where};
        """,
        [machine["machine_type"], machine["fuel_type"], *fleet_params],
    )
    stats = cur.fetchone()

    cur.execute(
        f"""
        SELECT COALESCE(status, 'UNKNOWN') AS status, COUNT(*) AS total
        FROM machines m
        WHERE {fleet_where}
        GROUP BY status
        ORDER BY status;
        """,
        fleet_params,
    )
    status_breakdown = cur.fetchall()

    cur.execute(
        f"""
        SELECT m.*, l.name AS center_name
        FROM machines m
        LEFT JOIN locations l ON m.center_id=l.id
        WHERE {fleet_where} AND m.id<>%s
        ORDER BY m.created_at DESC, m.machine_name
        LIMIT 10;
        """,
        [*fleet_params, machine_id],
    )
    related_machines = cur.fetchall()

    close_db(conn, commit=False)
    return render_template(
        "machines/analytics.html",
        machine=machine,
        stats=stats,
        status_breakdown=status_breakdown,
        related_machines=related_machines,
    )

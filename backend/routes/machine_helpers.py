"""
machine_helpers.py - shared helpers for machine routes
"""
from flask import render_template

from ..validation import clean_choice, clean_optional_text, clean_text, parse_optional_int


MACHINE_STATUS_OPTIONS = ("AVAILABLE", "IN USE", "MAINTENANCE", "OUT OF SERVICE")


def validate_machine_form(form):
    status = clean_choice(
        form.get("status"),
        "Status",
        MACHINE_STATUS_OPTIONS,
        required=False,
    ) or "AVAILABLE"
    return {
        "center_id": parse_optional_int(form.get("center_id"), "Center"),
        "machine_name": clean_text(form.get("machine_name"), "Machine name", required=True, max_length=150),
        "machine_type": clean_optional_text(form.get("machine_type"), "Machine type", max_length=100),
        "machine_number": clean_optional_text(form.get("machine_number"), "Machine number", max_length=100),
        "capacity": clean_optional_text(form.get("capacity"), "Capacity", max_length=50),
        "fuel_type": clean_optional_text(form.get("fuel_type"), "Fuel type", max_length=50),
        "status": status,
        "remarks": clean_optional_text(form.get("remarks"), "Remarks", max_length=2000, multiline=True),
    }


def render_machine_form(*, machine, centers, action, form_data=None, form_error_popup=None):
    return render_template(
        "machines/form.html",
        machine=machine,
        centers=centers,
        action=action,
        machine_status_options=MACHINE_STATUS_OPTIONS,
        form_data=form_data or {},
        form_error_popup=form_error_popup,
    )


def parse_machine_search(args):
    return clean_text(args.get("q", ""), "Search", max_length=100)


def build_machine_scope(role, assigned_loc_id):
    query = (
        "SELECT m.*, l.name AS center_name "
        "FROM machines m "
        "LEFT JOIN locations l ON m.center_id=l.id "
        "WHERE m.is_deleted=FALSE"
    )
    params = []
    if role == "teacher" and assigned_loc_id:
        query += " AND m.center_id=%s"
        params.append(assigned_loc_id)
    return query, params


def apply_machine_search(query, params, search):
    if search:
        query += (
            " AND (m.machine_name ILIKE %s OR COALESCE(m.machine_type,'') ILIKE %s"
            " OR COALESCE(m.machine_number,'') ILIKE %s OR COALESCE(m.capacity,'') ILIKE %s"
            " OR COALESCE(m.fuel_type,'') ILIKE %s OR COALESCE(m.status,'') ILIKE %s"
            " OR COALESCE(l.name,'') ILIKE %s)"
        )
        params.extend([f"%{search}%"] * 7)
    return query, params


def fetch_machine(cur, machine_id, *, role=None, assigned_loc_id=None):
    query = (
        "SELECT m.*, l.name AS center_name "
        "FROM machines m "
        "LEFT JOIN locations l ON m.center_id=l.id "
        "WHERE m.id=%s AND m.is_deleted=FALSE"
    )
    params = [machine_id]
    if role == "teacher" and assigned_loc_id:
        query += " AND m.center_id=%s"
        params.append(assigned_loc_id)
    cur.execute(query + ";", params)
    return cur.fetchone()


def load_machine_centers(cur, role, assigned_loc_id):
    if role == "teacher" and assigned_loc_id:
        cur.execute("SELECT id,name FROM locations WHERE id=%s ORDER BY position,name;", (assigned_loc_id,))
    else:
        cur.execute("SELECT id,name FROM locations ORDER BY position,name;")
    return cur.fetchall()

"""
channel_partner_helpers.py - helpers for channel partner routes
"""
from flask import render_template

from ..validation import clean_text, clean_optional_text, parse_optional_int


def validate_channel_partner_form(form):
    name = clean_text(form.get("name"), "Name", required=True, max_length=150)
    phone = clean_optional_text(form.get("phone"), "Phone", max_length=50)
    address = clean_optional_text(form.get("address"), "Address", max_length=1000, multiline=True)
    email = clean_optional_text(form.get("email"), "Email", max_length=200)
    trainer_id = parse_optional_int(form.get("trainer_id"), "Trainer")
    return {"name": name, "phone": phone, "address": address, "email": email, "trainer_id": trainer_id}


def render_channel_partner_form(*, partner, trainers, action, form_data=None, form_error_popup=None):
    return render_template(
        "channel_partners/form.html",
        partner=partner,
        trainers=trainers,
        action=action,
        form_data=form_data or {},
        form_error_popup=form_error_popup,
    )


def parse_channel_partner_search(args):
    return clean_text(args.get("q", ""), "Search", max_length=100)


def build_channel_partner_scope(role, assigned_loc_id):
    query = (
        "SELECT cp.*, u.username AS trainer_name, l.name AS trainer_location_name "
        "FROM channel_partners cp "
        "LEFT JOIN users u ON cp.trainer_id=u.id "
        "LEFT JOIN locations l ON u.location_id=l.id "
        "WHERE 1=1"
    )
    params = []
    return query, params


def apply_channel_partner_search(query, params, search):
    if search:
        query += " AND (cp.name ILIKE %s OR COALESCE(cp.phone,'') ILIKE %s OR COALESCE(cp.email,'') ILIKE %s OR COALESCE(cp.address,'') ILIKE %s)"
        params.extend([f"%{search}%"] * 4)
    return query, params


def fetch_channel_partner(cur, cp_id):
    cur.execute("SELECT cp.*, u.username AS trainer_name, u.location_id AS trainer_location_id FROM channel_partners cp LEFT JOIN users u ON cp.trainer_id=u.id WHERE cp.id=%s;", (cp_id,))
    return cur.fetchone()


def load_trainers(cur):
    cur.execute("SELECT id, username, location_id FROM users WHERE role='teacher' ORDER BY username;")
    return cur.fetchall()

"""
franchise_helpers.py - helpers for franchise routes
"""
from flask import render_template

from ..validation import (
    clean_text,
    clean_optional_text,
    clean_choice,
    parse_optional_int,
)


def validate_franchise_form(form):
    code = clean_text(form.get("code"), "Franchise code", required=True, max_length=50)
    name = clean_text(form.get("name"), "Franchise name", required=True, max_length=150)
    phone = clean_optional_text(form.get("phone"), "Phone", max_length=50)
    address = clean_optional_text(form.get("address"), "Address", max_length=1000, multiline=True)
    return {"code": code, "name": name, "phone": phone, "address": address}


def render_franchise_form(*, franchise, action, form_data=None, form_error_popup=None):
    return render_template(
        "franchises/form.html",
        franchise=franchise,
        action=action,
        form_data=form_data or {},
        form_error_popup=form_error_popup,
    )


def parse_franchise_search(args):
    return clean_text(args.get("q", ""), "Search", max_length=100)


def apply_franchise_search(query, params, search):
    if search:
        query += (
            " AND (code ILIKE %s OR name ILIKE %s OR COALESCE(phone,'') ILIKE %s"
            " OR COALESCE(address,'') ILIKE %s)"
        )
        params.extend([f"%{search}%"] * 4)
    return query, params


def build_franchise_scope(role, assigned_loc_id):
    # simple scope placeholder for future location scoping
    query = "SELECT * FROM franchises WHERE 1=1"
    params = []
    return query, params


def fetch_franchise(cur, fr_id):
    cur.execute("SELECT * FROM franchises WHERE id=%s;", (fr_id,))
    return cur.fetchone()


def load_franchise_sales_execs(cur, fr_id):
    cur.execute("SELECT * FROM sales_executives WHERE franchise_id=%s ORDER BY created_at DESC;", (fr_id,))
    return cur.fetchall()


def validate_sales_exec_form(form):
    name = clean_text(form.get("name"), "Name", required=True, max_length=150)
    phone = clean_optional_text(form.get("phone"), "Phone", max_length=50)
    address = clean_optional_text(form.get("address"), "Address", max_length=1000, multiline=True)
    email = clean_optional_text(form.get("email"), "Email", max_length=200)
    remarks = clean_optional_text(form.get("remarks"), "Remarks", max_length=2000, multiline=True)
    return {"name": name, "phone": phone, "address": address, "email": email, "remarks": remarks}


def render_sales_exec_form(*, franchise, action, sales_exec=None, form_data=None, form_error_popup=None):
    return render_template(
        "franchises/sales_exec_form.html",
        franchise=franchise,
        sales_exec=sales_exec,
        action=action,
        form_data=form_data or {},
        form_error_popup=form_error_popup,
    )


def fetch_sales_exec(cur, se_id):
    cur.execute("SELECT * FROM sales_executives WHERE id=%s;", (se_id,))
    return cur.fetchone()

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import get_db, close_db


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def has_table(cur, table_name):
    cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s;", (table_name,))
    return bool(cur.fetchone())


def has_column(cur, table_name, column_name):
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s;
        """,
        (table_name, column_name),
    )
    return bool(cur.fetchone())


conn = get_db()
cur = conn.cursor()

try:
    # Schema checks
    for table in ("franchises", "sales_executives", "channel_partners", "inquiries"):
        assert_true(has_table(cur, table), f"Missing table: {table}")

    for col in (
        "ref1_payment_method",
        "ref1_channel_partner_id",
        "ref1_franchise_id",
        "ref1_sales_exec_id",
        "ref2_payment_method",
        "ref3_payment_method",
    ):
        assert_true(has_column(cur, "inquiries", col), f"Missing inquiries column: {col}")

    # CRUD checks for new tables
    cur.execute(
        "INSERT INTO franchises (code,name,phone,address) VALUES (%s,%s,%s,%s) RETURNING id;",
        ("FSQA01", "Franchise QA", "9111111111", "QA Address"),
    )
    franchise_id = cur.fetchone()["id"]

    cur.execute(
        "INSERT INTO sales_executives (franchise_id,name,phone,email,address,remarks) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id;",
        (franchise_id, "Sales QA", "9222222222", "sales.qa@example.com", "QA", "ok"),
    )
    sales_exec_id = cur.fetchone()["id"]

    cur.execute(
        "INSERT INTO channel_partners (name,phone,email,address) VALUES (%s,%s,%s,%s) RETURNING id;",
        ("CP QA", "9333333333", "cp.qa@example.com", "CP Address"),
    )
    cp_id = cur.fetchone()["id"]

    # Inquiry link-field update check against an existing record
    cur.execute("SELECT id FROM inquiries ORDER BY id LIMIT 1;")
    inquiry = cur.fetchone()
    assert_true(bool(inquiry), "No inquiry row found to verify reference link update")
    inquiry_id = inquiry["id"]

    cur.execute(
        """
        UPDATE inquiries
        SET ref1_type=%s,
            ref1_name=%s,
            ref1_mobile=%s,
            ref1_amount_paid=%s,
            ref1_payment_method=%s,
            ref1_channel_partner_id=%s,
            ref1_franchise_id=%s,
            ref1_sales_exec_id=%s
        WHERE id=%s;
        """,
        (
            "Franchise",
            "Sales QA",
            "9222222222",
            123.45,
            "upi",
            cp_id,
            franchise_id,
            sales_exec_id,
            inquiry_id,
        ),
    )

    cur.execute(
        "SELECT ref1_type, ref1_payment_method, ref1_channel_partner_id, ref1_franchise_id, ref1_sales_exec_id FROM inquiries WHERE id=%s;",
        (inquiry_id,),
    )
    check = cur.fetchone()
    assert_true(check["ref1_type"] == "Franchise", "ref1_type not updated")
    assert_true(check["ref1_payment_method"] == "upi", "ref1_payment_method not updated")
    assert_true(check["ref1_channel_partner_id"] == cp_id, "ref1_channel_partner_id not updated")
    assert_true(check["ref1_franchise_id"] == franchise_id, "ref1_franchise_id not updated")
    assert_true(check["ref1_sales_exec_id"] == sales_exec_id, "ref1_sales_exec_id not updated")

    # Cleanup test rows
    cur.execute("DELETE FROM channel_partners WHERE id=%s;", (cp_id,))
    cur.execute("DELETE FROM sales_executives WHERE id=%s;", (sales_exec_id,))
    cur.execute("DELETE FROM franchises WHERE id=%s;", (franchise_id,))

    close_db(conn)
    print("Verification successful: schema + CRUD + inquiry reference linkage")
except Exception:
    close_db(conn, commit=False)
    raise

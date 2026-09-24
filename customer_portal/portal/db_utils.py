from django.db import connection


def refresh_pk_after_insert(instance):
    """Several models in this app (Customer, Motorcycle, Invoice, etc.)
    declare a plain IntegerField primary key rather than a real Django
    AutoField, because they're managed=False tables mirroring the desktop
    app's schema. The DB column is still a genuine auto-incrementing
    integer primary key (SQLite rowid, or MySQL AUTO_INCREMENT), but
    Django only fetches the inserted id back automatically for genuine
    AutoField columns, so instance.pk stays None after save() otherwise.
    Pull the real id back directly; safe here since exactly one INSERT
    happens on this connection between save() and this call.

    Uses the engine-appropriate "last insert id" function since these
    tables may live on either SQLite (dev) or MySQL (production, shared
    with the desktop app)."""
    query = 'SELECT LAST_INSERT_ID()' if connection.vendor == 'mysql' else 'SELECT last_insert_rowid()'
    with connection.cursor() as cursor:
        cursor.execute(query)
        instance.pk = cursor.fetchone()[0]
    return instance

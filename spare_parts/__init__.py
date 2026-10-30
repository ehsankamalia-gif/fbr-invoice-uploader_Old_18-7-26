"""Spare Parts Management module - wholesale + retail.

INDEPENDENCE RULES (read before editing anything in this package):

1. This package never imports from any other app package (app.qt_ui,
   app.services, app.db.models, app.api, etc.). The one sanctioned
   exception is reusing the main app's DATABASE CONNECTION as a generic
   shared utility - see spare_parts/db/base.py - because the user
   explicitly chose "same database, same connection" over a second
   database. That import touches no table/model from the rest of the
   app, only the SQLAlchemy engine/session factory object itself.

2. Every table this package creates is prefixed `sp_` and defined on its
   own SQLAlchemy declarative base (SpareBase, in spare_parts/db/base.py)
   - never on app.db.models.Base. No foreign key, join, or query in this
   package ever references a non-`sp_` table. This module keeps its own
   customers, suppliers, categories - it never reuses app.db.models.Customer
   or Supplier.

   ONE explicit, narrow exception (requested 2026-10-12): the printed
   receipt's company-name header reads the main app's `companies.name`
   via a single read-only raw SQL query over the shared connection (see
   ui/sale_card_widget.py's _get_main_app_company_name) - not an ORM
   import of app.db.models.Company, not a join, never written to. This
   is the only such exception in the package; any future read like it
   must be documented here the same way.

3. The only change this module makes to existing app files is ONE menu
   entry in app/qt_ui/main_window.py that opens
   spare_parts.ui.main_widget.SparePartsModuleWidget as a page. Every
   later phase of this module adds tabs/screens *inside* that one widget,
   not new changes to main_window.py.

4. This module never touches the Invoice form, invoice_service, or
   anything that builds the FBR submission payload. It has no FBR
   integration.

5. Deleting this spare_parts/ folder and the one menu entry in
   main_window.py must leave the rest of the app running normally - this
   package is never imported anywhere except that one menu entry.

6. Tables are created/upgraded only by spare_parts/db/migrations.py
   (idempotent, versioned, tracked in its own sp_schema_migrations
   table) - never by ad-hoc DDL elsewhere in this package.
"""

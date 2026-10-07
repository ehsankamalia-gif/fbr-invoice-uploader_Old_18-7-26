from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0009_add_company_id_to_portal_auth'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='staffaccess',
            options={
                'default_permissions': (),
                'managed': False,
                'permissions': [
                    ('view_dashboard', 'View admin dashboard'),
                    ('view_customers', 'View customers'),
                    ('view_customer_summary', 'View customer summary'),
                    ('view_sales', 'View credit sales'),
                    ('view_payments', 'View payments'),
                    ('view_inventory', 'View inventory'),
                    ('view_transactions', 'View transaction history'),
                    ('view_portal_accounts', 'View customer portal accounts'),
                    ('manage_portal_accounts', 'Create/reset/block customer portal accounts'),
                    ('view_old_credit_ledger', 'View old running credit ledger'),
                    ('view_finance_credit_ledger', 'View advance separate finance ledger'),
                    ('view_combined_ledger', 'View combined credit ledger'),
                    ('view_spare_ledger', 'View spare parts ledger'),
                    ('export_data', 'Export sales/payments to CSV'),
                    ('manage_customers', 'Add/edit customer records'),
                    ('manage_product_models', 'Add/edit/delete product models'),
                    ('manage_inventory', 'Add/edit/delete motorcycles'),
                    ('manage_finance_sales', 'Add/edit/delete finance credit sales'),
                    ('manage_finance_installments', 'Add/edit/delete finance installments'),
                    ('manage_finance_ledger', 'Add/edit/delete finance ledger entries'),
                    ('view_invoices', 'View submitted sales invoices'),
                    ('create_invoices', 'Create new sales invoices and upload them to FBR'),
                    ('manage_fbr_config', 'View & edit FBR configuration (POS ID, tokens, active environment)'),
                ],
            },
        ),
        # The column itself was already dropped directly against MySQL by
        # the desktop app's own single-company-revert migration (both apps
        # share this physical table) - state-only here so Django's recorded
        # model history matches the real schema without trying to DROP a
        # column that's already gone.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='customerportalauth',
                    name='company_id',
                ),
            ],
            database_operations=[],
        ),
    ]

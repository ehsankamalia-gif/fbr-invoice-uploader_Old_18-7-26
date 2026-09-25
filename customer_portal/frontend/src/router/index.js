import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '../stores/auth';

import CustomerLayout from '../layouts/CustomerLayout.vue';
import AdminLayout from '../layouts/AdminLayout.vue';

import CustomerLoginView from '../views/customer/LoginView.vue';
import CustomerDashboardView from '../views/customer/DashboardView.vue';
import LoanDetailView from '../views/customer/LoanDetailView.vue';
import CustomerPaymentsView from '../views/customer/PaymentsView.vue';
import ProfileView from '../views/customer/ProfileView.vue';
import RunningLedgerView from '../views/customer/RunningLedgerView.vue';

import AdminLoginView from '../views/admin/LoginView.vue';
import AdminDashboardView from '../views/admin/DashboardView.vue';
import NoAccessView from '../views/admin/NoAccessView.vue';
import CustomersView from '../views/admin/CustomersView.vue';
import CustomerSummaryView from '../views/admin/CustomerSummaryView.vue';
import CustomerDetailView from '../views/admin/CustomerDetailView.vue';
import CustomerLedgerView from '../views/admin/CustomerLedgerView.vue';
import SalesView from '../views/admin/SalesView.vue';
import AdminPaymentsView from '../views/admin/PaymentsView.vue';
import InventoryView from '../views/admin/InventoryView.vue';
import TransactionsView from '../views/admin/TransactionsView.vue';
import OldCreditLedgerView from '../views/admin/OldCreditLedgerView.vue';
import FinanceCreditLedgerView from '../views/admin/FinanceCreditLedgerView.vue';
import CombinedLedgerView from '../views/admin/CombinedLedgerView.vue';
import SpareLedgerTransactionsView from '../views/admin/SpareLedgerTransactionsView.vue';
import SpareLedgerMonthlyReportView from '../views/admin/SpareLedgerMonthlyReportView.vue';
import SpareLedgerMonthlySummaryView from '../views/admin/SpareLedgerMonthlySummaryView.vue';

import ManageCustomersView from '../views/admin/ManageCustomersView.vue';
import CustomerFormView from '../views/admin/CustomerFormView.vue';
import ManageProductModelsView from '../views/admin/ManageProductModelsView.vue';
import ProductModelFormView from '../views/admin/ProductModelFormView.vue';
import MotorcycleFormView from '../views/admin/MotorcycleFormView.vue';
import FinanceSaleFormView from '../views/admin/FinanceSaleFormView.vue';
import ManageFinanceInstallmentsView from '../views/admin/ManageFinanceInstallmentsView.vue';
import FinanceInstallmentFormView from '../views/admin/FinanceInstallmentFormView.vue';
import ManageFinanceLedgerView from '../views/admin/ManageFinanceLedgerView.vue';
import FinanceLedgerFormView from '../views/admin/FinanceLedgerFormView.vue';
import PortalAccountsView from '../views/admin/PortalAccountsView.vue';
import PortalAccountFormView from '../views/admin/PortalAccountFormView.vue';
import StaffListView from '../views/admin/StaffListView.vue';
import StaffFormView from '../views/admin/StaffFormView.vue';
import StaffPermissionsView from '../views/admin/StaffPermissionsView.vue';
import InvoicesView from '../views/admin/InvoicesView.vue';
import InvoiceFormView from '../views/admin/InvoiceFormView.vue';
import FBRConfigView from '../views/admin/FBRConfigView.vue';
import CompaniesView from '../views/admin/CompaniesView.vue';

const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', name: 'customer-login', component: CustomerLoginView, meta: { area: 'customer' } },
  {
    path: '/',
    component: CustomerLayout,
    meta: { area: 'customer', requiresAuth: true },
    children: [
      { path: 'dashboard', name: 'customer-dashboard', component: CustomerDashboardView },
      { path: 'loan/:loanType/:loanId', name: 'customer-loan-detail', component: LoanDetailView, props: true },
      { path: 'payments', name: 'customer-payments', component: CustomerPaymentsView },
      { path: 'profile', name: 'customer-profile', component: ProfileView },
      { path: 'running-ledger', name: 'customer-running-ledger', component: RunningLedgerView },
    ],
  },

  { path: '/custom-admin/login', name: 'admin-login', component: AdminLoginView, meta: { area: 'admin' } },
  {
    path: '/custom-admin',
    component: AdminLayout,
    meta: { area: 'admin', requiresAuth: true },
    children: [
      { path: '', name: 'admin-dashboard', component: AdminDashboardView, meta: { perm: 'view_dashboard' } },
      { path: 'no-access', name: 'admin-no-access', component: NoAccessView },
      { path: 'customers', name: 'admin-customers', component: CustomersView, meta: { perm: 'view_customers' } },
      { path: 'customer-summary', name: 'admin-customer-summary', component: CustomerSummaryView, meta: { perm: 'view_customer_summary' } },
      { path: 'customer/:id', name: 'admin-customer-detail', component: CustomerDetailView, props: true, meta: { perm: 'view_customer_summary' } },
      { path: 'customer/:id/ledger', name: 'admin-customer-ledger', component: CustomerLedgerView, props: true, meta: { perm: 'view_customer_summary' } },
      { path: 'sales', name: 'admin-sales', component: SalesView, meta: { perm: 'view_sales' } },
      { path: 'payments', name: 'admin-payments', component: AdminPaymentsView, meta: { perm: 'view_payments' } },
      { path: 'inventory', name: 'admin-inventory', component: InventoryView, meta: { perm: 'view_inventory' } },
      { path: 'transactions', name: 'admin-transactions', component: TransactionsView, meta: { perm: 'view_transactions' } },
      { path: 'old-credit-ledger', name: 'admin-old-credit-ledger', component: OldCreditLedgerView, meta: { perm: 'view_old_credit_ledger' } },
      { path: 'finance-credit-ledger', name: 'admin-finance-credit-ledger', component: FinanceCreditLedgerView, meta: { perm: 'view_finance_credit_ledger' } },
      { path: 'combined-credit-ledger', name: 'admin-combined-ledger', component: CombinedLedgerView, meta: { perm: 'view_combined_ledger' } },
      { path: 'spare-ledger-transactions', name: 'admin-spare-ledger-transactions', component: SpareLedgerTransactionsView, meta: { perm: 'view_spare_ledger' } },
      { path: 'spare-ledger-monthly-report', name: 'admin-spare-ledger-monthly-report', component: SpareLedgerMonthlyReportView, meta: { perm: 'view_spare_ledger' } },
      { path: 'spare-ledger-monthly-summary', name: 'admin-spare-ledger-monthly-summary', component: SpareLedgerMonthlySummaryView, meta: { perm: 'view_spare_ledger' } },

      // --- Phase 3: admin CRUD ("Manage Data") ---
      { path: 'manage/customers', name: 'admin-manage-customers', component: ManageCustomersView, meta: { perm: 'manage_customers' } },
      { path: 'manage/customers/create', name: 'admin-manage-customer-create', component: CustomerFormView, meta: { perm: 'manage_customers' } },
      { path: 'manage/customers/:id/edit', name: 'admin-manage-customer-edit', component: CustomerFormView, props: true, meta: { perm: 'manage_customers' } },

      { path: 'manage/product-models', name: 'admin-manage-product-models', component: ManageProductModelsView, meta: { perm: 'manage_product_models' } },
      { path: 'manage/product-models/create', name: 'admin-manage-product-model-create', component: ProductModelFormView, meta: { perm: 'manage_product_models' } },
      { path: 'manage/product-models/:id/edit', name: 'admin-manage-product-model-edit', component: ProductModelFormView, props: true, meta: { perm: 'manage_product_models' } },

      { path: 'manage/motorcycles/create', name: 'admin-manage-motorcycle-create', component: MotorcycleFormView, meta: { perm: 'manage_inventory' } },
      { path: 'manage/motorcycles/:id/edit', name: 'admin-manage-motorcycle-edit', component: MotorcycleFormView, props: true, meta: { perm: 'manage_inventory' } },

      { path: 'manage/finance-sales/create', name: 'admin-manage-finance-sale-create', component: FinanceSaleFormView, meta: { perm: 'manage_finance_sales' } },
      { path: 'manage/finance-sales/:id/edit', name: 'admin-manage-finance-sale-edit', component: FinanceSaleFormView, props: true, meta: { perm: 'manage_finance_sales' } },

      { path: 'manage/finance-installments', name: 'admin-manage-finance-installments', component: ManageFinanceInstallmentsView, meta: { perm: 'manage_finance_installments' } },
      { path: 'manage/finance-installments/create', name: 'admin-manage-finance-installment-create', component: FinanceInstallmentFormView, meta: { perm: 'manage_finance_installments' } },
      { path: 'manage/finance-installments/:id/edit', name: 'admin-manage-finance-installment-edit', component: FinanceInstallmentFormView, props: true, meta: { perm: 'manage_finance_installments' } },

      { path: 'manage/finance-ledger', name: 'admin-manage-finance-ledger', component: ManageFinanceLedgerView, meta: { perm: 'manage_finance_ledger' } },
      { path: 'manage/finance-ledger/create', name: 'admin-manage-finance-ledger-create', component: FinanceLedgerFormView, meta: { perm: 'manage_finance_ledger' } },
      { path: 'manage/finance-ledger/:id/edit', name: 'admin-manage-finance-ledger-edit', component: FinanceLedgerFormView, props: true, meta: { perm: 'manage_finance_ledger' } },

      { path: 'invoices', name: 'admin-invoices', component: InvoicesView, meta: { perm: 'view_invoices' } },
      { path: 'invoices/create', name: 'admin-invoice-create', component: InvoiceFormView, meta: { perm: 'create_invoices' } },
      { path: 'invoices/fbr-config', name: 'admin-fbr-config', component: FBRConfigView, meta: { perm: 'manage_fbr_config' } },

      { path: 'portal-auths', name: 'admin-portal-accounts', component: PortalAccountsView, meta: { perm: 'view_portal_accounts' } },
      { path: 'portal-auths/create', name: 'admin-portal-account-create', component: PortalAccountFormView, meta: { perm: 'manage_portal_accounts' } },
      { path: 'portal-auths/:id/edit', name: 'admin-portal-account-edit', component: PortalAccountFormView, props: true, meta: { perm: 'manage_portal_accounts' } },

      { path: 'companies', name: 'admin-companies', component: CompaniesView, meta: { perm: 'manage_companies' } },

      // --- Phase 4: Staff Management (Admin-only, governs access to everything else) ---
      { path: 'staff', name: 'admin-staff-list', component: StaffListView, meta: { adminOnly: true } },
      { path: 'staff/create', name: 'admin-staff-create', component: StaffFormView, meta: { adminOnly: true } },
      { path: 'staff/:id/permissions', name: 'admin-staff-permissions', component: StaffPermissionsView, props: true, meta: { adminOnly: true } },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!auth.ready) {
    try {
      await auth.fetchSession();
    } catch (e) {
      auth.ready = true;
    }
  }

  if (to.meta.area === 'customer' && to.meta.requiresAuth && auth.role !== 'customer') {
    return { name: 'customer-login', query: { next: to.fullPath } };
  }
  if (to.name === 'customer-login' && auth.role === 'customer') {
    return { name: 'customer-dashboard' };
  }

  if (to.meta.area === 'admin' && to.meta.requiresAuth) {
    if (!auth.isStaffOrAdmin) {
      return { name: 'admin-login', query: { next: to.fullPath } };
    }
    if (to.meta.adminOnly && auth.role !== 'admin') {
      return { name: 'admin-no-access' };
    }
    if (to.meta.perm && !auth.can(to.meta.perm)) {
      return { name: 'admin-no-access' };
    }
  }
  if (to.name === 'admin-login' && auth.isStaffOrAdmin) {
    return { name: 'admin-dashboard' };
  }

  return true;
});

export default router;

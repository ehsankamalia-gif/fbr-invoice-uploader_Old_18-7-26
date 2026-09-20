import api from './client';

export const getDashboard = () => api.get('admin/dashboard/').then((r) => r.data);
export const getCustomers = () => api.get('admin/customers/').then((r) => r.data);
export const getCustomerSummary = (search) =>
  api.get('admin/customer-summary/', { params: search ? { search } : {} }).then((r) => r.data);
export const getCustomerDetail = (id) => api.get(`admin/customer-summary/${id}/`).then((r) => r.data);
export const getCustomerLedger = (id) => api.get(`admin/customer-summary/${id}/ledger/`).then((r) => r.data);
export const getSales = () => api.get('admin/sales/').then((r) => r.data);
export const getPayments = () => api.get('admin/payments/').then((r) => r.data);
export const getInventory = () => api.get('admin/inventory/').then((r) => r.data);
export const getTransactions = () => api.get('admin/transactions/').then((r) => r.data);
export const getOldCreditLedger = () => api.get('admin/ledgers/old-credit/').then((r) => r.data);
export const getFinanceCreditLedger = () => api.get('admin/ledgers/finance-credit/').then((r) => r.data);
export const getCombinedLedger = () => api.get('admin/ledgers/combined/').then((r) => r.data);
export const getSpareLedgerTransactions = (params) =>
  api.get('admin/spare-ledger/transactions/', { params }).then((r) => r.data);
export const getSpareLedgerMonthlyReport = () => api.get('admin/spare-ledger/monthly-report/').then((r) => r.data);
export const getSpareLedgerMonthlySummary = () => api.get('admin/spare-ledger/monthly-summary/').then((r) => r.data);

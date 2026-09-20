import api from './client';

// Shared dropdown options
export const getCustomerOptions = () => api.get('admin/options/customers/').then((r) => r.data);
export const getFinanceSaleOptions = () => api.get('admin/options/finance-sales/').then((r) => r.data);

// Customers
export const listManageCustomers = (search) =>
  api.get('admin/manage/customers/', { params: search ? { search } : {} }).then((r) => r.data);
export const getManageCustomer = (id) => api.get(`admin/manage/customers/${id}/`).then((r) => r.data);
export const createManageCustomer = (data) => api.post('admin/manage/customers/', data).then((r) => r.data);
export const updateManageCustomer = (id, data) => api.put(`admin/manage/customers/${id}/`, data).then((r) => r.data);
export const toggleCustomerDeleted = (id) => api.post(`admin/manage/customers/${id}/toggle-deleted/`).then((r) => r.data);

// Product Models
export const listProductModels = () => api.get('admin/manage/product-models/').then((r) => r.data);
export const getProductModel = (id) => api.get(`admin/manage/product-models/${id}/`).then((r) => r.data);
export const createProductModel = (data) => api.post('admin/manage/product-models/', data).then((r) => r.data);
export const updateProductModel = (id, data) => api.put(`admin/manage/product-models/${id}/`, data).then((r) => r.data);
export const deleteProductModel = (id) => api.delete(`admin/manage/product-models/${id}/`);

// Motorcycles
export const getMotorcycle = (id) => api.get(`admin/manage/motorcycles/${id}/`).then((r) => r.data);
export const createMotorcycle = (data) => api.post('admin/manage/motorcycles/', data).then((r) => r.data);
export const updateMotorcycle = (id, data) => api.put(`admin/manage/motorcycles/${id}/`, data).then((r) => r.data);
export const deleteMotorcycle = (id) => api.delete(`admin/manage/motorcycles/${id}/`);

// Finance Credit Sales
export const getFinanceSale = (id) => api.get(`admin/manage/finance-sales/${id}/`).then((r) => r.data);
export const createFinanceSale = (data) => api.post('admin/manage/finance-sales/', data).then((r) => r.data);
export const updateFinanceSale = (id, data) => api.put(`admin/manage/finance-sales/${id}/`, data).then((r) => r.data);
export const deleteFinanceSale = (id) => api.delete(`admin/manage/finance-sales/${id}/`);

// Finance Installments
export const listFinanceInstallments = () => api.get('admin/manage/finance-installments/').then((r) => r.data);
export const getFinanceInstallment = (id) => api.get(`admin/manage/finance-installments/${id}/`).then((r) => r.data);
export const createFinanceInstallment = (data) => api.post('admin/manage/finance-installments/', data).then((r) => r.data);
export const updateFinanceInstallment = (id, data) => api.put(`admin/manage/finance-installments/${id}/`, data).then((r) => r.data);
export const deleteFinanceInstallment = (id) => api.delete(`admin/manage/finance-installments/${id}/`);

// Finance Ledger
export const listFinanceLedgerEntries = () => api.get('admin/manage/finance-ledger/').then((r) => r.data);
export const getFinanceLedgerEntry = (id) => api.get(`admin/manage/finance-ledger/${id}/`).then((r) => r.data);
export const createFinanceLedgerEntry = (data) => api.post('admin/manage/finance-ledger/', data).then((r) => r.data);
export const updateFinanceLedgerEntry = (id, data) => api.put(`admin/manage/finance-ledger/${id}/`, data).then((r) => r.data);
export const deleteFinanceLedgerEntry = (id) => api.delete(`admin/manage/finance-ledger/${id}/`);

// Portal Accounts
export const listPortalAccounts = () => api.get('admin/manage/portal-accounts/').then((r) => r.data);
export const getPortalAccount = (id) => api.get(`admin/manage/portal-accounts/${id}/`).then((r) => r.data);
export const createPortalAccount = (customerId) =>
  api.post('admin/manage/portal-accounts/', { customer: customerId }).then((r) => r.data);
export const updatePortalAccount = (id, data) => api.put(`admin/manage/portal-accounts/${id}/`, data).then((r) => r.data);
export const resetPortalAccountPassword = (id) => api.post(`admin/manage/portal-accounts/${id}/reset-password/`).then((r) => r.data);
export const togglePortalAccountActive = (id) => api.post(`admin/manage/portal-accounts/${id}/toggle-active/`).then((r) => r.data);
export const getEligibleCustomers = () => api.get('admin/manage/portal-accounts/eligible-customers/').then((r) => r.data);

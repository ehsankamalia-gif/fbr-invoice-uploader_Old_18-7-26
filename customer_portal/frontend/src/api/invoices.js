import api from './client';

export const getInvoiceFormOptions = () => api.get('admin/invoices/options/').then((r) => r.data);
export const getInvoicePricePreview = (motorcycleId) =>
  api.get(`admin/invoices/price-preview/${motorcycleId}/`).then((r) => r.data);
export const createInvoice = (data) => api.post('admin/invoices/create/', data).then((r) => r.data);
export const listInvoices = (search) =>
  api.get('admin/invoices/', { params: search ? { search } : {} }).then((r) => r.data);

import api from './client';

export const getDashboard = () => api.get('customer/dashboard/').then((r) => r.data);
export const getLoanDetail = (loanType, loanId) =>
  api.get(`customer/loans/${loanType}/${loanId}/`).then((r) => r.data);
export const getPayments = () => api.get('customer/payments/').then((r) => r.data);
export const getProfile = () => api.get('customer/profile/').then((r) => r.data);
export const getRunningLedger = () => api.get('customer/running-ledger/').then((r) => r.data);

import api from './client';

export const getCompanies = () => api.get('admin/companies/').then((r) => r.data);
export const createCompany = (data) => api.post('admin/companies/', data).then((r) => r.data);
export const updateCompany = (id, data) => api.put(`admin/companies/${id}/`, data).then((r) => r.data);
export const activateCompany = (id) => api.post(`admin/companies/${id}/activate/`).then((r) => r.data);

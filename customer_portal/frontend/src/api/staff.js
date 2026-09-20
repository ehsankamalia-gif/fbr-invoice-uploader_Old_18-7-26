import api from './client';

export const listStaff = () => api.get('admin/staff/').then((r) => r.data);
export const createStaff = (data) => api.post('admin/staff/create/', data).then((r) => r.data);
export const getStaffPermissions = (userId) => api.get(`admin/staff/${userId}/permissions/`).then((r) => r.data);
export const saveStaffPermissions = (userId, data) => api.put(`admin/staff/${userId}/permissions/`, data).then((r) => r.data);
export const toggleStaffActive = (userId) => api.post(`admin/staff/${userId}/toggle-active/`).then((r) => r.data);
export const resetStaffPassword = (userId) => api.post(`admin/staff/${userId}/reset-password/`).then((r) => r.data);

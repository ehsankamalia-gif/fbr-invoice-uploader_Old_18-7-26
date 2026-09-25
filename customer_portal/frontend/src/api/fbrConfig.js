import api from './client';

export const getFbrConfig = () => api.get('admin/fbr-config/').then((r) => r.data);
export const updateFbrConfig = (environment, data) =>
  api.put(`admin/fbr-config/${environment}/`, data).then((r) => r.data);
export const activateFbrEnvironment = (environment) =>
  api.post(`admin/fbr-config/${environment}/activate/`).then((r) => r.data);

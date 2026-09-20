import api from './client';

export function fetchSession() {
  return api.get('auth/session/').then((r) => r.data);
}

export function loginCustomer(phoneNumber, password) {
  return api.post('auth/customer/login/', { phone_number: phoneNumber, password }).then((r) => r.data);
}

export function logoutCustomer() {
  return api.post('auth/customer/logout/').then((r) => r.data);
}

export function loginStaff(username, password) {
  return api.post('auth/staff/login/', { username, password }).then((r) => r.data);
}

export function logoutStaff() {
  return api.post('auth/staff/logout/').then((r) => r.data);
}

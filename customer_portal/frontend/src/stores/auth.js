import { defineStore } from 'pinia';
import * as authApi from '../api/auth';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    role: null, // 'anonymous' | 'customer' | 'staff' | 'admin'
    customer: null,
    user: null,
    permissions: [],
    ready: false,
  }),
  getters: {
    isCustomer: (state) => state.role === 'customer',
    isStaffOrAdmin: (state) => state.role === 'staff' || state.role === 'admin',
    // Mirrors {% if perms.portal.xxx %}: Django's has_perm() auto-returns
    // True for superusers regardless of whether the permission is actually
    // assigned, so 'admin' bypasses the permissions list entirely here too.
    can: (state) => (code) => state.role === 'admin' || state.permissions.includes(code),
  },
  actions: {
    _applySession(data) {
      this.role = data.role;
      this.customer = data.customer || null;
      this.user = data.user || null;
      this.permissions = (data.user && data.user.permissions) || [];
    },
    async fetchSession() {
      const data = await authApi.fetchSession();
      this._applySession(data);
      this.ready = true;
      return data;
    },
    async loginCustomer(phoneNumber, password) {
      const data = await authApi.loginCustomer(phoneNumber, password);
      this.role = 'customer';
      this.customer = data.customer;
      this.user = null;
      this.permissions = [];
    },
    async loginStaff(username, password) {
      const data = await authApi.loginStaff(username, password);
      this.role = data.user.role;
      this.user = data.user;
      this.customer = null;
      this.permissions = data.user.permissions || [];
    },
    async logout() {
      if (this.role === 'customer') {
        await authApi.logoutCustomer();
      } else if (this.isStaffOrAdmin) {
        await authApi.logoutStaff();
      }
      this.role = 'anonymous';
      this.customer = null;
      this.user = null;
      this.permissions = [];
    },
  },
});

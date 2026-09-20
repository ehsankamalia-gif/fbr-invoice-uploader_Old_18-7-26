<script setup>
import { ref, onMounted } from 'vue';
import { useAuthStore } from '../../stores/auth';
import { listPortalAccounts, resetPortalAccountPassword, togglePortalAccountActive } from '../../api/manage';
import { fmtDateTime } from '../../utils/format';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const auth = useAuthStore();
const loading = ref(true);
const accounts = ref([]);

async function load() {
  const data = await listPortalAccounts();
  accounts.value = data.results || data;
}

async function resetPassword(account) {
  if (!confirm(`Reset password for ${account.customer_name} to the default (123456789)?`)) return;
  await resetPortalAccountPassword(account.id);
  alert(`Password reset for ${account.customer_name}.`);
}

async function toggleActive(account) {
  const updated = await togglePortalAccountActive(account.id);
  const idx = accounts.value.findIndex((a) => a.id === account.id);
  if (idx !== -1) accounts.value[idx] = updated;
}

onMounted(async () => {
  await load();
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8 flex justify-between items-center">
      <div>
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-user-shield mr-3"></i>Customer Portal Accounts</h1>
        <p class="text-gray-600">Manage customer portal credentials</p>
      </div>
      <router-link
        v-if="auth.can('manage_portal_accounts')"
        :to="{ name: 'admin-portal-account-create' }"
        class="px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all"
      >
        <i class="fas fa-plus mr-2"></i>Create Account
      </router-link>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-6 card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Customer</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Phone (Username)</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Status</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Created At</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="account in accounts" :key="account.id" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-4 px-4 text-sm text-gray-800">{{ account.id }}</td>
              <td class="py-4 px-4 text-sm font-medium text-gray-800">{{ account.customer_name }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ account.phone_number }}</td>
              <td class="py-4 px-4">
                <span
                  class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium"
                  :class="account.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'"
                >
                  <i class="fas mr-1" :class="account.is_active ? 'fa-check-circle' : 'fa-ban'"></i>
                  {{ account.is_active ? 'Active' : 'Blocked' }}
                </span>
              </td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ fmtDateTime(account.created_at) }}</td>
              <td class="py-4 px-4">
                <div v-if="auth.can('manage_portal_accounts')" class="flex items-center space-x-2">
                  <router-link
                    :to="{ name: 'admin-portal-account-edit', params: { id: account.id } }"
                    class="px-3 py-1.5 bg-blue-500 text-white text-sm rounded-lg hover:bg-blue-600 transition"
                  >
                    <i class="fas fa-edit mr-1"></i>Edit
                  </router-link>
                  <button @click="resetPassword(account)" class="px-3 py-1.5 bg-yellow-500 text-white text-sm rounded-lg hover:bg-yellow-600 transition">
                    <i class="fas fa-key mr-1"></i>Reset Password
                  </button>
                  <button
                    @click="toggleActive(account)"
                    class="px-3 py-1.5 text-white text-sm rounded-lg transition"
                    :class="account.is_active ? 'bg-red-500 hover:bg-red-600' : 'bg-green-500 hover:bg-green-600'"
                  >
                    <i class="fas mr-1" :class="account.is_active ? 'fa-user-slash' : 'fa-user-check'"></i>
                    {{ account.is_active ? 'Block' : 'Unblock' }}
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!accounts.length">
              <td colspan="6" class="py-12 text-center text-gray-500">
                <i class="fas fa-inbox fa-3x mb-3"></i>
                <p class="text-lg">No portal accounts found</p>
                <p class="text-sm mt-1">Click "Create Account" to add a new one</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

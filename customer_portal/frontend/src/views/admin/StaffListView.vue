<script setup>
import { ref, onMounted } from 'vue';
import { useAuthStore } from '../../stores/auth';
import { listStaff, resetStaffPassword, toggleStaffActive } from '../../api/staff';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const auth = useAuthStore();
const loading = ref(true);
const staffUsers = ref([]);

async function load() {
  staffUsers.value = await listStaff();
}

async function resetPassword(user) {
  if (!confirm(`Reset password for ${user.username}?`)) return;
  const data = await resetStaffPassword(user.id);
  alert(
    `Password reset for ${user.username}. Temporary password: ${data.temp_password} ` +
      '(share this with them securely - it will not be shown again).'
  );
}

async function toggleActive(user) {
  try {
    const updated = await toggleStaffActive(user.id);
    const idx = staffUsers.value.findIndex((u) => u.id === user.id);
    if (idx !== -1) staffUsers.value[idx] = updated;
  } catch (e) {
    alert(e.response?.data?.detail || 'Could not update this account.');
  }
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
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-user-cog mr-3"></i>Staff & Admin Accounts</h1>
        <p class="text-gray-600">Admins have full access. Staff only see what you grant them.</p>
      </div>
      <router-link
        :to="{ name: 'admin-staff-create' }"
        class="px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all"
      >
        <i class="fas fa-plus mr-2"></i>Add Staff / Admin
      </router-link>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-6 card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Username</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Email</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Role</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Status</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in staffUsers" :key="user.id" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-4 px-4 text-sm font-medium text-gray-800">
                {{ user.username }}
                <span v-if="user.username === auth.user?.username" class="text-xs text-gray-400">(you)</span>
              </td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ user.email || '-' }}</td>
              <td class="py-4 px-4">
                <span v-if="user.is_superuser" class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-700">
                  <i class="fas fa-crown mr-1"></i>Admin
                </span>
                <span v-else class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
                  <i class="fas fa-user mr-1"></i>Staff
                </span>
              </td>
              <td class="py-4 px-4">
                <span
                  class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium"
                  :class="user.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'"
                >
                  <i class="fas mr-1" :class="user.is_active ? 'fa-check-circle' : 'fa-ban'"></i>
                  {{ user.is_active ? 'Active' : 'Deactivated' }}
                </span>
              </td>
              <td class="py-4 px-4">
                <div class="flex items-center space-x-2">
                  <router-link
                    :to="{ name: 'admin-staff-permissions', params: { id: user.id } }"
                    class="px-3 py-1.5 bg-blue-500 text-white text-sm rounded-lg hover:bg-blue-600 transition"
                  >
                    <i class="fas fa-sliders-h mr-1"></i>Manage Access
                  </router-link>
                  <button @click="resetPassword(user)" class="px-3 py-1.5 bg-yellow-500 text-white text-sm rounded-lg hover:bg-yellow-600 transition">
                    <i class="fas fa-key mr-1"></i>Reset Password
                  </button>
                  <button
                    v-if="user.username !== auth.user?.username"
                    @click="toggleActive(user)"
                    class="px-3 py-1.5 text-white text-sm rounded-lg transition"
                    :class="user.is_active ? 'bg-red-500 hover:bg-red-600' : 'bg-green-500 hover:bg-green-600'"
                  >
                    <i class="fas mr-1" :class="user.is_active ? 'fa-user-slash' : 'fa-user-check'"></i>
                    {{ user.is_active ? 'Deactivate' : 'Activate' }}
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!staffUsers.length">
              <td colspan="5" class="py-12 text-center text-gray-500">
                <i class="fas fa-inbox fa-3x mb-3"></i>
                <p class="text-lg">No staff accounts yet</p>
                <p class="text-sm mt-1">Click "Add Staff / Admin" to create one</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

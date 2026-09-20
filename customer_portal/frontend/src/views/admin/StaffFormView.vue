<script setup>
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { createStaff } from '../../api/staff';

const router = useRouter();
const form = reactive({ username: '', email: '', password: '', role: 'STAFF' });
const error = ref('');
const saving = ref(false);

async function submit() {
  error.value = '';
  saving.value = true;
  try {
    const user = await createStaff(form);
    if (user.role === 'ADMIN') {
      router.push({ name: 'admin-staff-list' });
    } else {
      router.push({ name: 'admin-staff-permissions', params: { id: user.id } });
    }
  } catch (e) {
    error.value = e.response?.data?.detail || 'Could not create this account.';
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div>
    <div class="mb-8">
      <router-link :to="{ name: 'admin-staff-list' }" class="text-blue-500 hover:text-blue-600 mb-4 inline-flex items-center">
        <i class="fas fa-arrow-left mr-2"></i>Back to Staff & Admin Accounts
      </router-link>
      <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-user-plus mr-3"></i>Add Staff / Admin</h1>
      <p class="text-gray-600">Create a login for a staff member or another admin</p>
    </div>

    <div class="bg-white rounded-xl p-8 card-shadow max-w-2xl">
      <div v-if="error" class="mb-6 px-4 py-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
        {{ error }}
      </div>

      <form @submit.prevent="submit">
        <div class="mb-6">
          <label class="block text-sm font-semibold text-gray-700 mb-2">
            <i class="fas fa-user mr-2 text-gray-500"></i>Username
          </label>
          <input
            type="text" v-model="form.username" required
            class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
          />
        </div>

        <div class="mb-6">
          <label class="block text-sm font-semibold text-gray-700 mb-2">
            <i class="fas fa-envelope mr-2 text-gray-500"></i>Email (optional)
          </label>
          <input
            type="email" v-model="form.email"
            class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
          />
        </div>

        <div class="mb-6">
          <label class="block text-sm font-semibold text-gray-700 mb-2">
            <i class="fas fa-lock mr-2 text-gray-500"></i>Password
          </label>
          <input
            type="password" v-model="form.password" required minlength="8"
            class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
          />
          <p class="text-sm text-gray-500 mt-2">At least 8 characters.</p>
        </div>

        <div class="mb-6">
          <label class="block text-sm font-semibold text-gray-700 mb-3">
            <i class="fas fa-user-tag mr-2 text-gray-500"></i>Role
          </label>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label
              class="flex items-start p-4 border-2 rounded-lg cursor-pointer transition"
              :class="form.role === 'STAFF' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-blue-400'"
            >
              <input type="radio" v-model="form.role" value="STAFF" class="mt-1 mr-3" />
              <span>
                <span class="block font-semibold text-gray-800">Staff</span>
                <span class="block text-sm text-gray-500">You choose exactly which pages they can access, right after creating the account.</span>
              </span>
            </label>
            <label
              class="flex items-start p-4 border-2 rounded-lg cursor-pointer transition"
              :class="form.role === 'ADMIN' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-blue-400'"
            >
              <input type="radio" v-model="form.role" value="ADMIN" class="mt-1 mr-3" />
              <span>
                <span class="block font-semibold text-gray-800">Admin</span>
                <span class="block text-sm text-gray-500">Full access to everything, including staff management.</span>
              </span>
            </label>
          </div>
        </div>

        <div class="flex justify-end space-x-4">
          <router-link :to="{ name: 'admin-staff-list' }" class="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300 transition">
            Cancel
          </router-link>
          <button type="submit" :disabled="saving" class="px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all disabled:opacity-60">
            <i class="fas fa-check mr-2"></i>{{ saving ? 'Creating...' : 'Create Account' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

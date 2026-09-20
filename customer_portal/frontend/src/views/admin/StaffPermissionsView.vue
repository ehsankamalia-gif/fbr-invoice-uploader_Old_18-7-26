<script setup>
import { ref, reactive, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getStaffPermissions, saveStaffPermissions } from '../../api/staff';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const route = useRoute();
const router = useRouter();

const loading = ref(true);
const saving = ref(false);
const error = ref('');
const target = ref(null);
const isSelf = ref(false);
const modules = ref([]);
const role = ref('STAFF');
const selectedCodes = reactive(new Set());

function toggleCode(code) {
  if (selectedCodes.has(code)) selectedCodes.delete(code);
  else selectedCodes.add(code);
}

async function submit() {
  error.value = '';
  saving.value = true;
  try {
    await saveStaffPermissions(route.params.id, {
      role: role.value,
      permissions: Array.from(selectedCodes),
    });
    router.push({ name: 'admin-staff-list' });
  } catch (e) {
    error.value = e.response?.data?.detail || 'Could not save changes.';
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  const data = await getStaffPermissions(route.params.id);
  target.value = data.user;
  isSelf.value = data.is_self;
  modules.value = data.modules;
  role.value = data.role;
  data.current_codenames.forEach((code) => selectedCodes.add(code));
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8">
      <router-link :to="{ name: 'admin-staff-list' }" class="text-blue-500 hover:text-blue-600 mb-4 inline-flex items-center">
        <i class="fas fa-arrow-left mr-2"></i>Back to Staff & Admin Accounts
      </router-link>
      <h1 class="text-3xl font-bold text-gray-800 mb-2">
        <i class="fas fa-sliders-h mr-3"></i>Manage Access{{ target ? ` - ${target.username}` : '' }}
      </h1>
      <p class="text-gray-600">Choose the role for this account and, for Staff, exactly which pages they can open.</p>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-8 card-shadow max-w-3xl">
      <div v-if="error" class="mb-6 px-4 py-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
        {{ error }}
      </div>

      <form @submit.prevent="submit">
        <div class="mb-6">
          <label class="block text-sm font-semibold text-gray-700 mb-3">
            <i class="fas fa-user-tag mr-2 text-gray-500"></i>Role
          </label>

          <template v-if="isSelf">
            <p class="text-sm text-gray-500 mb-2">You can't change your own role.</p>
            <div class="px-4 py-3 border-2 border-purple-300 bg-purple-50 rounded-lg font-semibold text-purple-700 inline-block">
              <i class="fas fa-crown mr-2"></i>Admin (full access)
            </div>
          </template>
          <div v-else class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label
              class="flex items-start p-4 border-2 rounded-lg cursor-pointer transition"
              :class="role === 'STAFF' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-blue-400'"
            >
              <input type="radio" v-model="role" value="STAFF" class="mt-1 mr-3" />
              <span>
                <span class="block font-semibold text-gray-800">Staff</span>
                <span class="block text-sm text-gray-500">Access limited to the pages you tick below.</span>
              </span>
            </label>
            <label
              class="flex items-start p-4 border-2 rounded-lg cursor-pointer transition"
              :class="role === 'ADMIN' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-blue-400'"
            >
              <input type="radio" v-model="role" value="ADMIN" class="mt-1 mr-3" />
              <span>
                <span class="block font-semibold text-gray-800">Admin</span>
                <span class="block text-sm text-gray-500">Full access to everything, including staff management.</span>
              </span>
            </label>
          </div>
        </div>

        <div v-if="role === 'STAFF' && !isSelf" class="mb-6">
          <label class="block text-sm font-semibold text-gray-700 mb-3">
            <i class="fas fa-th-large mr-2 text-gray-500"></i>Pages this Staff account can access
          </label>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-gray-50 rounded-lg p-4">
            <label
              v-for="[code, label] in modules" :key="code"
              class="flex items-center px-3 py-2 bg-white rounded-lg border border-gray-200 cursor-pointer hover:border-blue-400 transition"
            >
              <input type="checkbox" :checked="selectedCodes.has(code)" @change="toggleCode(code)" class="mr-3" />
              <span class="text-sm text-gray-700">{{ label }}</span>
            </label>
          </div>
        </div>

        <div class="flex justify-end space-x-4">
          <router-link :to="{ name: 'admin-staff-list' }" class="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300 transition">
            Cancel
          </router-link>
          <button type="submit" :disabled="saving" class="px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all disabled:opacity-60">
            <i class="fas fa-check mr-2"></i>{{ saving ? 'Saving...' : 'Save Access' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

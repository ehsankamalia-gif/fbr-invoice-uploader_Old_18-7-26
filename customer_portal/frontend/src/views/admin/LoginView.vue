<script setup>
import { ref } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAuthStore } from '../../stores/auth';

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const username = ref('');
const password = ref('');
const error = ref('');
const loading = ref(false);

async function submit() {
  error.value = '';
  loading.value = true;
  try {
    await auth.loginStaff(username.value, password.value);
    router.push(route.query.next || { name: 'admin-dashboard' });
  } catch (e) {
    error.value = e.response?.data?.errors?.__all__?.[0] || 'Invalid username or password.';
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center px-4 py-12" style="background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 50%, #2563eb 100%);">
    <div class="max-w-md w-full bg-white rounded-2xl shadow-2xl p-8">
      <div class="text-center mb-8">
        <div class="w-20 h-20 bg-gradient-to-br from-blue-500 to-blue-600 rounded-full flex items-center justify-center mx-auto mb-4 shadow-lg">
          <i class="fas fa-motorcycle text-3xl text-white"></i>
        </div>
        <h3 class="text-2xl font-bold text-gray-800 mb-2 tracking-tight">BikeZone Admin Portal</h3>
        <p class="text-gray-500">Sign in with your staff or admin account</p>
      </div>

      <form @submit.prevent="submit" class="space-y-6">
        <div v-if="error" class="p-4 bg-red-50 text-red-700 rounded-lg border border-red-200">
          <i class="fas fa-exclamation-circle mr-2"></i>{{ error }}
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">
            <i class="fas fa-user mr-2 text-gray-500"></i>Username
          </label>
          <input
            v-model="username"
            type="text"
            required
            autofocus
            placeholder="Username"
            class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">
            <i class="fas fa-lock mr-2 text-gray-500"></i>Password
          </label>
          <input
            v-model="password"
            type="password"
            required
            placeholder="Password"
            class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
          />
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="w-full py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg shadow-lg hover:shadow-xl transition-all duration-300 disabled:opacity-60"
        >
          <i class="fas fa-sign-in-alt mr-2"></i>{{ loading ? 'Signing in...' : 'Sign In' }}
        </button>
      </form>
    </div>
  </div>
</template>

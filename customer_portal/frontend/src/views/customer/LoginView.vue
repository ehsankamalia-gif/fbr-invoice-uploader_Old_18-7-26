<script setup>
import { ref } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAuthStore } from '../../stores/auth';

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const phoneNumber = ref('');
const password = ref('');
const error = ref('');
const loading = ref(false);

async function submit() {
  error.value = '';
  loading.value = true;
  try {
    await auth.loginCustomer(phoneNumber.value, password.value);
    router.push(route.query.next || { name: 'customer-dashboard' });
  } catch (e) {
    const errors = e.response?.data?.errors;
    error.value = errors?.__all__?.[0] || errors?.password?.[0] || errors?.phone_number?.[0] || 'Invalid phone number or password';
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center gradient-bg px-4 py-12">
    <div class="max-w-md w-full bg-white rounded-2xl shadow-2xl p-8">
      <div class="text-center mb-8">
        <div class="w-20 h-20 bg-gradient-to-br from-blue-500 to-blue-600 rounded-full flex items-center justify-center mx-auto mb-4 shadow-lg">
          <i class="fas fa-motorcycle text-3xl text-white"></i>
        </div>
        <h3 class="text-2xl font-bold text-gray-800 mb-2 tracking-tight">Customer Portal</h3>
        <p class="text-gray-500">Sign in to view your account</p>
      </div>

      <form @submit.prevent="submit" class="space-y-6">
        <div v-if="error" class="p-4 bg-red-50 text-red-700 rounded-lg border border-red-200">
          <i class="fas fa-exclamation-circle mr-2"></i>{{ error }}
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">
            <i class="fas fa-phone mr-2 text-gray-500"></i>Phone Number
          </label>
          <input
            v-model="phoneNumber"
            type="text"
            required
            placeholder="Enter your phone number"
            class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition bg-gray-50 hover:bg-white"
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
            placeholder="Enter your password"
            class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition bg-gray-50 hover:bg-white"
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

      <div class="text-center mt-8">
        <p class="text-gray-500 text-sm">
          <i class="fas fa-info-circle mr-1"></i>
          Don't have an account? Please contact administration.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const sidebarOpen = ref(false);

const navItems = [
  { name: 'customer-dashboard', label: 'Dashboard', icon: 'fas fa-home' },
  { name: 'customer-payments', label: 'Payment History', icon: 'fas fa-credit-card' },
  { name: 'customer-running-ledger', label: 'Running Ledger', icon: 'fas fa-book' },
  { name: 'customer-profile', label: 'My Profile', icon: 'fas fa-user' },
];

async function logout() {
  await auth.logout();
  router.push({ name: 'customer-login' });
}
</script>

<template>
  <div class="flex min-h-screen bg-gray-50">
    <div
      v-if="sidebarOpen"
      class="sidebar-overlay fixed inset-0 z-40 md:hidden"
      @click="sidebarOpen = false"
    ></div>

    <aside
      class="w-64 bg-gradient-to-b from-primary-800 to-primary-900 text-white flex flex-col fixed md:relative z-50 h-screen transition-transform duration-300"
      :class="sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'"
    >
      <div class="p-6 border-b border-white/10">
        <h1 class="text-2xl font-bold flex items-center">
          <i class="fas fa-motorcycle mr-3"></i>
          BikeZone
        </h1>
        <p class="text-sm text-white/60 mt-1">Customer Portal</p>
      </div>

      <nav class="flex-1 p-4 overflow-y-auto">
        <router-link
          v-for="item in navItems"
          :key="item.name"
          :to="{ name: item.name }"
          class="sidebar-link flex items-center px-4 py-3 rounded-lg mb-2"
          :class="{ 'active bg-white/15': route.name === item.name }"
        >
          <i :class="item.icon" class="w-6 mr-3"></i>
          {{ item.label }}
        </router-link>
      </nav>

      <div class="p-4 border-t border-white/10">
        <button
          @click="logout"
          class="w-full flex items-center px-4 py-3 rounded-lg bg-red-500/20 hover:bg-red-500/30 transition"
        >
          <i class="fas fa-sign-out-alt w-6 mr-3"></i>
          Logout
        </button>
      </div>
    </aside>

    <main class="flex-1">
      <header class="md:hidden bg-white border-b border-gray-200 p-4 flex items-center justify-between sticky top-0 z-30">
        <button class="p-2 rounded-lg text-gray-600 hover:bg-gray-100 transition" @click="sidebarOpen = true">
          <i class="fas fa-bars text-xl"></i>
        </button>
        <h1 class="text-xl font-bold text-gray-800">BikeZone</h1>
        <div class="w-10"></div>
      </header>

      <header class="hidden md:block bg-white border-b border-gray-200 px-8 py-4">
        <div class="flex justify-between items-center">
          <div>
            <h2 class="text-xl font-semibold text-gray-800">{{ auth.customer?.name }}</h2>
            <p class="text-sm text-gray-500">
              <i class="fas fa-calendar-alt mr-2"></i>
              {{ auth.customer?.type ? auth.customer.type.charAt(0) + auth.customer.type.slice(1).toLowerCase() : '' }} Account
            </p>
          </div>
          <i class="fas fa-user-circle text-2xl text-gray-600"></i>
        </div>
      </header>

      <div class="p-4 md:p-8">
        <router-view />
      </div>
    </main>
  </div>
</template>

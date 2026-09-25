<script setup>
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const sidebarOpen = ref(false);

let storedCollapsed = false;
try {
  storedCollapsed = localStorage.getItem('customer_sidebar_collapsed') === 'true';
} catch (e) {
  storedCollapsed = false;
}
const collapsed = ref(storedCollapsed);
function toggleCollapsed() {
  collapsed.value = !collapsed.value;
  try {
    localStorage.setItem('customer_sidebar_collapsed', String(collapsed.value));
  } catch (e) {
    // ignore (private browsing / storage blocked) - the toggle still works for this page view
  }
}

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
      class="bg-gradient-to-b from-primary-800 to-primary-900 text-white flex flex-col fixed md:relative z-50 h-screen transition-all duration-300"
      :class="[collapsed ? 'md:w-20' : 'md:w-64', 'w-64', sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0']"
    >
      <div class="p-6 border-b border-white/10 relative">
        <template v-if="!collapsed">
          <h1 class="text-2xl font-bold flex items-center">
            <i class="fas fa-motorcycle mr-3"></i>
            BikeZone
          </h1>
          <p class="text-sm text-white/60 mt-1">Customer Portal</p>
        </template>
        <div v-else class="flex justify-center">
          <i class="fas fa-motorcycle text-2xl"></i>
        </div>
        <button
          type="button"
          @click="toggleCollapsed"
          class="hidden md:flex items-center justify-center absolute -right-3 top-7 w-6 h-6 bg-white text-gray-700 rounded-full shadow hover:bg-gray-100 transition z-10"
          :title="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
        >
          <i class="fas text-xs" :class="collapsed ? 'fa-chevron-right' : 'fa-chevron-left'"></i>
        </button>
      </div>

      <nav class="flex-1 p-4 overflow-y-auto">
        <router-link
          v-for="item in navItems"
          :key="item.name"
          :to="{ name: item.name }"
          class="sidebar-link flex items-center rounded-lg mb-2"
          :class="[collapsed ? 'justify-center px-2 py-3' : 'px-4 py-3', { 'active bg-white/15': route.name === item.name }]"
          :title="collapsed ? item.label : ''"
        >
          <i :class="[item.icon, { 'w-6 mr-3': !collapsed }]"></i>
          <span v-if="!collapsed">{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="p-4 border-t border-white/10">
        <button
          v-if="!collapsed"
          @click="logout"
          class="w-full flex items-center px-4 py-3 rounded-lg bg-red-500/20 hover:bg-red-500/30 transition"
        >
          <i class="fas fa-sign-out-alt w-6 mr-3"></i>
          Logout
        </button>
        <button
          v-else
          @click="logout"
          class="w-full flex items-center justify-center px-2 py-3 rounded-lg bg-red-500/20 hover:bg-red-500/30 transition"
          title="Logout"
        >
          <i class="fas fa-sign-out-alt"></i>
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

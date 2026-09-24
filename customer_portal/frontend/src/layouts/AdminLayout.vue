<script setup>
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const sidebarOpen = ref(false);

// Phases 1-4 of the SPA rewrite migrated Dashboard, all read-only reports,
// "Manage Data" CRUD, and Staff Management to real Vue routes.
const mainItems = [
  { perm: 'view_dashboard', label: 'Dashboard', icon: 'fas fa-tachometer-alt', routeName: 'admin-dashboard' },
  { perm: 'view_customers', label: 'Customers', icon: 'fas fa-users', routeName: 'admin-customers' },
  { perm: 'view_customer_summary', label: 'Customer Summary', icon: 'fas fa-chart-pie', routeName: 'admin-customer-summary' },
  { perm: 'view_sales', label: 'Credit Sales', icon: 'fas fa-shopping-cart', routeName: 'admin-sales' },
  { perm: 'view_payments', label: 'Payments', icon: 'fas fa-credit-card', routeName: 'admin-payments' },
  { perm: 'view_inventory', label: 'Inventory', icon: 'fas fa-motorcycle', routeName: 'admin-inventory' },
  { perm: 'view_invoices', label: 'Invoices', icon: 'fas fa-file-invoice', routeName: 'admin-invoices' },
  { perm: 'view_transactions', label: 'Transactions', icon: 'fas fa-history', routeName: 'admin-transactions' },
  { perm: 'view_portal_accounts', label: 'Portal Accounts', icon: 'fas fa-user-shield', routeName: 'admin-portal-accounts' },
];

const ledgerItems = [
  { perm: 'view_old_credit_ledger', label: 'Old Running Credit', icon: 'fas fa-book-open', routeName: 'admin-old-credit-ledger' },
  { perm: 'view_finance_credit_ledger', label: 'Advance Separate Finance', icon: 'fas fa-wallet', routeName: 'admin-finance-credit-ledger' },
  { perm: 'view_combined_ledger', label: 'Combined Ledger', icon: 'fas fa-layer-group', routeName: 'admin-combined-ledger' },
  { perm: 'view_spare_ledger', label: 'Spare Parts Ledger', icon: 'fas fa-exchange-alt', routeName: 'admin-spare-ledger-transactions' },
  { perm: 'view_spare_ledger', label: 'Monthly Report', icon: 'fas fa-calendar-alt', routeName: 'admin-spare-ledger-monthly-report' },
  { perm: 'view_spare_ledger', label: 'Monthly Summary', icon: 'fas fa-calendar', routeName: 'admin-spare-ledger-monthly-summary' },
];

const manageItems = [
  { perm: 'manage_customers', label: 'Customers', icon: 'fas fa-address-book', routeName: 'admin-manage-customers' },
  { perm: 'manage_product_models', label: 'Product Models', icon: 'fas fa-cogs', routeName: 'admin-manage-product-models' },
  { perm: 'manage_finance_installments', label: 'Finance Installments', icon: 'fas fa-hand-holding-usd', routeName: 'admin-manage-finance-installments' },
  { perm: 'manage_finance_ledger', label: 'Finance Ledger', icon: 'fas fa-book', routeName: 'admin-manage-finance-ledger' },
];

async function logout() {
  await auth.logout();
  router.push({ name: 'admin-login' });
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
      class="sidebar-gradient w-64 text-white flex flex-col fixed md:relative z-50 h-screen transition-transform duration-300"
      :class="sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'"
    >
      <div class="p-6 border-b border-white/10">
        <h1 class="text-2xl font-bold flex items-center">
          <i class="fas fa-motorcycle mr-3"></i>
          BikeZone
        </h1>
        <p class="text-sm text-white/60 mt-1">Admin Portal</p>
      </div>

      <nav class="flex-1 p-4 overflow-y-auto">
        <template v-for="item in mainItems" :key="item.label">
          <router-link
            v-if="item.routeName && auth.can(item.perm)"
            :to="{ name: item.routeName }"
            class="sidebar-link flex items-center px-4 py-3 rounded-lg mb-2"
            :class="{ 'active bg-white/15': route.name === item.routeName }"
          >
            <i :class="item.icon" class="w-6 mr-3"></i>{{ item.label }}
          </router-link>
          <a
            v-else-if="auth.can(item.perm)"
            :href="item.href"
            class="sidebar-link flex items-center px-4 py-3 rounded-lg mb-2"
          >
            <i :class="item.icon" class="w-6 mr-3"></i>{{ item.label }}
          </a>
        </template>

        <template v-if="ledgerItems.some((i) => auth.can(i.perm))">
          <div class="border-t border-white/10 my-4"></div>
          <div class="text-xs uppercase text-white/50 font-semibold mb-2 px-2">Ledgers</div>
        </template>
        <template v-for="item in ledgerItems" :key="item.label">
          <router-link
            v-if="item.routeName && auth.can(item.perm)"
            :to="{ name: item.routeName }"
            class="sidebar-link flex items-center px-4 py-3 rounded-lg mb-2"
            :class="{ 'active bg-white/15': route.name === item.routeName }"
          >
            <i :class="item.icon" class="w-6 mr-3"></i>{{ item.label }}
          </router-link>
          <a
            v-else-if="auth.can(item.perm)"
            :href="item.href"
            class="sidebar-link flex items-center px-4 py-3 rounded-lg mb-2"
          >
            <i :class="item.icon" class="w-6 mr-3"></i>{{ item.label }}
          </a>
        </template>

        <template v-if="manageItems.some((i) => auth.can(i.perm))">
          <div class="border-t border-white/10 my-4"></div>
          <div class="text-xs uppercase text-white/50 font-semibold mb-2 px-2">Manage Data</div>
        </template>
        <router-link
          v-for="item in manageItems.filter((i) => auth.can(i.perm))"
          :key="item.label"
          :to="{ name: item.routeName }"
          class="sidebar-link flex items-center px-4 py-3 rounded-lg mb-2"
          :class="{ 'active bg-white/15': route.name === item.routeName }"
        >
          <i :class="item.icon" class="w-6 mr-3"></i>{{ item.label }}
        </router-link>

        <template v-if="auth.role === 'admin'">
          <div class="border-t border-white/10 my-4"></div>
          <div class="text-xs uppercase text-white/50 font-semibold mb-2 px-2">Administration</div>
          <router-link
            :to="{ name: 'admin-staff-list' }"
            class="sidebar-link flex items-center px-4 py-3 rounded-lg mb-2"
            :class="{ 'active bg-white/15': route.name && route.name.startsWith('admin-staff') }"
          >
            <i class="fas fa-user-cog w-6 mr-3"></i>Staff Management
          </router-link>
        </template>
      </nav>

      <div class="p-4 border-t border-white/10">
        <div class="flex items-center justify-between text-sm">
          <div class="min-w-0">
            <p class="font-semibold truncate">{{ auth.user?.username }}</p>
            <p class="text-white/50 text-xs">{{ auth.role === 'admin' ? 'Admin' : 'Staff' }}</p>
          </div>
          <button @click="logout" class="text-white/70 hover:text-white ml-2" title="Logout">
            <i class="fas fa-sign-out-alt"></i>
          </button>
        </div>
      </div>
    </aside>

    <main class="flex-1">
      <header class="md:hidden bg-white p-4 flex items-center justify-between border-b border-gray-200 sticky top-0 z-30">
        <button class="p-2 rounded-lg text-gray-600 hover:bg-gray-100 transition" @click="sidebarOpen = true">
          <i class="fas fa-bars text-xl"></i>
        </button>
        <h1 class="text-xl font-bold text-gray-800">BikeZone Admin</h1>
        <div class="w-10"></div>
      </header>

      <div class="p-4 md:p-8">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { getDashboard } from '../../api/admin';
import StatCard from '../../components/ui/StatCard.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const stats = ref(null);

function fmt(n) {
  return Number(n || 0).toFixed(0);
}
function fmtDate(d) {
  return new Date(d).toISOString().slice(0, 10);
}

onMounted(async () => {
  stats.value = await getDashboard();
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-800 mb-2">
        <i class="fas fa-tachometer-alt mr-3"></i>Admin Dashboard
      </h1>
      <p class="text-gray-600">Overview of your motorcycle credit business</p>
    </div>

    <LoadingSpinner v-if="loading" />

    <template v-else-if="stats">
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard label="Total Customers" :value="stats.total_customers" icon="fas fa-users" gradient="from-blue-500 to-blue-600" />
        <StatCard label="Credit Customers" :value="stats.total_credit_customers" icon="fas fa-hand-holding-usd" gradient="from-green-500 to-green-600" />
        <StatCard label="Total Sales" :value="stats.total_sales" icon="fas fa-shopping-cart" gradient="from-purple-500 to-purple-600" />
        <StatCard label="Total Outstanding" :value="`Rs. ${fmt(stats.total_outstanding)}`" icon="fas fa-money-bill-wave" gradient="from-red-500 to-red-600" value-class="text-red-600" />
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="bg-white rounded-xl p-6 card-shadow">
          <h5 class="text-lg font-semibold text-gray-800 mb-4 flex items-center">
            <i class="fas fa-clock mr-2 text-blue-500"></i>Recent Sales
          </h5>
          <div class="overflow-x-auto">
            <table class="w-full">
              <thead>
                <tr class="border-b border-gray-200">
                  <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">ID</th>
                  <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">Customer</th>
                  <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">Status</th>
                  <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">Date</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="sale in stats.recent_sales" :key="sale.id" class="border-b border-gray-100 hover:bg-gray-50">
                  <td class="py-3 px-2 text-sm text-gray-800">{{ sale.id }}</td>
                  <td class="py-3 px-2 text-sm font-medium text-gray-800">{{ sale.customer_name }}</td>
                  <td class="py-3 px-2">
                    <span
                      class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                      :class="{
                        'bg-green-100 text-green-800': sale.status === 'ACTIVE',
                        'bg-yellow-100 text-yellow-800': sale.status === 'OVERDUE',
                        'bg-gray-100 text-gray-800': !['ACTIVE', 'OVERDUE'].includes(sale.status),
                      }"
                    >{{ sale.status }}</span>
                  </td>
                  <td class="py-3 px-2 text-sm text-gray-600">{{ fmtDate(sale.sale_date) }}</td>
                </tr>
                <tr v-if="!stats.recent_sales.length">
                  <td colspan="4" class="py-8 text-center text-gray-500">
                    <i class="fas fa-inbox fa-2x mb-2"></i>
                    <p>No recent sales</p>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="bg-white rounded-xl p-6 card-shadow">
          <h5 class="text-lg font-semibold text-gray-800 mb-4 flex items-center">
            <i class="fas fa-credit-card mr-2 text-green-500"></i>Recent Payments
          </h5>
          <div class="overflow-x-auto">
            <table class="w-full">
              <thead>
                <tr class="border-b border-gray-200">
                  <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">ID</th>
                  <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">Customer</th>
                  <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">Amount</th>
                  <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">Date</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in stats.recent_payments" :key="p.id" class="border-b border-gray-100 hover:bg-gray-50">
                  <td class="py-3 px-2 text-sm text-gray-800">{{ p.id }}</td>
                  <td class="py-3 px-2 text-sm font-medium text-gray-800">{{ p.customer_name }}</td>
                  <td class="py-3 px-2 text-sm font-semibold text-green-600">Rs. {{ Number(p.paid_amount).toFixed(2) }}</td>
                  <td class="py-3 px-2 text-sm text-gray-600">{{ fmtDate(p.payment_date) }}</td>
                </tr>
                <tr v-if="!stats.recent_payments.length">
                  <td colspan="4" class="py-8 text-center text-gray-500">
                    <i class="fas fa-inbox fa-2x mb-2"></i>
                    <p>No recent payments</p>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="mb-8 mt-6">
        <h2 class="text-2xl font-bold text-gray-800 mb-4">
          <i class="fas fa-motorcycle mr-3"></i>Motorcycle Models (Sold on Credit)
        </h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          <div v-for="m in stats.motorcycles_by_model" :key="m.product_model__id" class="bg-white rounded-xl p-6 card-shadow card-hover">
            <div class="flex items-center justify-between mb-4">
              <h5 class="text-lg font-semibold text-gray-800">{{ m.product_model__model_name }}</h5>
              <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center">
                <i class="fas fa-motorcycle text-white"></i>
              </div>
            </div>
            <div class="space-y-3">
              <div class="flex items-center justify-between">
                <p class="text-sm text-gray-500">Total</p>
                <p class="text-xl font-bold text-gray-800">{{ m.count }}</p>
              </div>
              <div class="flex items-center justify-between">
                <p class="text-sm text-gray-500">In Stock</p>
                <p class="text-xl font-bold text-green-600">{{ m.in_stock }}</p>
              </div>
              <div class="flex items-center justify-between">
                <p class="text-sm text-gray-500">Sold</p>
                <p class="text-xl font-bold text-purple-600">{{ m.sold }}</p>
              </div>
            </div>
          </div>
          <div v-if="!stats.motorcycles_by_model.length" class="col-span-full py-12 text-center text-gray-500">
            <i class="fas fa-motorcycle fa-3x mb-3 text-gray-300"></i>
            <p class="text-lg">No motorcycle models found</p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

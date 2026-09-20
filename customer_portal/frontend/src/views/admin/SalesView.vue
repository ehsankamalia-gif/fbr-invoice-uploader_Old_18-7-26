<script setup>
import { ref, onMounted } from 'vue';
import { getSales } from '../../api/admin';
import { deleteFinanceSale } from '../../api/manage';
import { useAuthStore } from '../../stores/auth';
import { fmt, fmtDate } from '../../utils/format';
import StatusBadge from '../../components/ui/StatusBadge.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const auth = useAuthStore();
const loading = ref(true);
const sales = ref([]);

async function load() {
  const data = await getSales();
  sales.value = data.sales;
}

async function remove(sale) {
  if (!confirm(`Delete sale ${sale.sale_id}? This may still be referenced by other records.`)) return;
  await deleteFinanceSale(sale.id);
  sales.value = sales.value.filter((s) => !(s.type === sale.type && s.id === sale.id));
}

onMounted(async () => {
  await load();
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-shopping-cart mr-3"></i>Credit Sales</h1>
        <p class="text-gray-600">All credit sales records</p>
      </div>
      <div class="flex gap-3">
        <a href="/custom-admin/export-sales-csv/" class="inline-flex items-center px-4 py-2 bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 transition">
          <i class="fas fa-download mr-2"></i>Export CSV
        </a>
        <router-link
          v-if="auth.can('manage_finance_sales')"
          :to="{ name: 'admin-manage-finance-sale-create' }"
          class="inline-flex items-center px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium rounded-lg hover:shadow-lg transition"
        >
          <i class="fas fa-plus mr-2"></i>Add Sale
        </router-link>
      </div>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-6 card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Type</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Sale ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Customer</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Chassis No</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Status</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Remaining</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Date</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="sale in sales" :key="`${sale.type}-${sale.id}`" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-4 px-4 text-sm text-gray-600">{{ sale.type }}</td>
              <td class="py-4 px-4 text-sm text-gray-800">{{ sale.id }}</td>
              <td class="py-4 px-4 text-sm font-semibold text-gray-800">{{ sale.sale_id || '-' }}</td>
              <td class="py-4 px-4 text-sm text-gray-800">{{ sale.customer_name }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ sale.chassis_no || '-' }}</td>
              <td class="py-4 px-4"><StatusBadge :status="sale.status" /></td>
              <td class="py-4 px-4 text-sm font-bold" :class="sale.remaining_balance > 0 ? 'text-red-600' : 'text-green-600'">
                Rs. {{ sale.remaining_balance }}
              </td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ fmtDate(sale.sale_date) }}</td>
              <td class="py-4 px-4">
                <template v-if="sale.type === 'Finance' && auth.can('manage_finance_sales')">
                  <router-link :to="{ name: 'admin-manage-finance-sale-edit', params: { id: sale.id } }" class="text-blue-600 hover:text-blue-800 transition mr-3">
                    <i class="fas fa-edit"></i>
                  </router-link>
                  <button @click="remove(sale)" class="text-red-500 hover:text-red-700 transition">
                    <i class="fas fa-trash"></i>
                  </button>
                </template>
              </td>
            </tr>
            <tr v-if="!sales.length">
              <td colspan="9" class="py-12 text-center text-gray-500">
                <i class="fas fa-shopping-cart fa-3x mb-3 text-gray-300"></i>
                <p class="text-lg">No sales found</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

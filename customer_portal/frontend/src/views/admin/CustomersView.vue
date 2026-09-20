<script setup>
import { ref, onMounted } from 'vue';
import { getCustomers } from '../../api/admin';
import { useAuthStore } from '../../stores/auth';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const auth = useAuthStore();
const loading = ref(true);
const customers = ref([]);

onMounted(async () => {
  const data = await getCustomers();
  customers.value = data.customers;
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-users mr-3"></i>Credit Customers</h1>
        <p class="text-gray-600">Manage all your customers</p>
      </div>
      <a
        v-if="auth.can('manage_customers')"
        href="/custom-admin/manage/customers/create/"
        class="inline-flex items-center px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium rounded-lg hover:shadow-lg transition"
      >
        <i class="fas fa-plus mr-2"></i>Add Customer
      </a>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-6 card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Name</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Type</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Phone</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">CNIC</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Credit Sales</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Outstanding</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in customers" :key="item.id" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-4 px-4 text-sm text-gray-800">{{ item.id }}</td>
              <td class="py-4 px-4 text-sm font-semibold text-gray-800">{{ item.name }}</td>
              <td class="py-4 px-4">
                <span
                  class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                  :class="item.type === 'DEALER' ? 'bg-blue-100 text-blue-800' : 'bg-green-100 text-green-800'"
                >{{ item.type }}</span>
              </td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ item.phone || '-' }}</td>
              <td class="py-4 px-4 text-sm text-gray-500">{{ item.cnic || '-' }}</td>
              <td class="py-4 px-4 text-sm font-medium text-gray-800">{{ item.credit_sales_count }}</td>
              <td class="py-4 px-4 text-sm font-bold" :class="item.total_outstanding > 0 ? 'text-red-600' : 'text-green-600'">
                Rs. {{ item.total_outstanding || 0 }}
              </td>
              <td class="py-4 px-4">
                <router-link
                  :to="{ name: 'admin-customer-ledger', params: { id: item.id } }"
                  class="text-green-600 hover:text-green-800 mr-3"
                >
                  <i class="fas fa-book"></i>
                </router-link>
                <a
                  v-if="auth.can('manage_customers')"
                  :href="`/custom-admin/manage/customers/${item.id}/edit/`"
                  class="text-blue-600 hover:text-blue-800 transition"
                >
                  <i class="fas fa-edit"></i>
                </a>
              </td>
            </tr>
            <tr v-if="!customers.length">
              <td colspan="8" class="py-12 text-center text-gray-500">
                <i class="fas fa-users fa-3x mb-3 text-gray-300"></i>
                <p class="text-lg">No customers found</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { getPayments } from '../../api/admin';
import { useAuthStore } from '../../stores/auth';
import { fmt, fmtDate } from '../../utils/format';
import StatusBadge from '../../components/ui/StatusBadge.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const auth = useAuthStore();
const loading = ref(true);
const payments = ref([]);
const totalAmount = ref(0);

onMounted(async () => {
  const data = await getPayments();
  payments.value = data.payments;
  totalAmount.value = data.total_amount;
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-credit-card mr-3"></i>Payments</h1>
        <p class="text-gray-600">All payment records (advance, installments, etc)</p>
      </div>
      <a href="/custom-admin/export-payments-csv/" class="inline-flex items-center px-6 py-3 bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 transition">
        <i class="fas fa-download mr-2"></i>Export CSV
      </a>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-6 card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Payment ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Type</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Customer</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Description</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Amount</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Status</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Date</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in payments" :key="`${p.type}-${p.id}`" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-4 px-4 text-sm text-gray-800">{{ p.id }}</td>
              <td class="py-4 px-4 text-sm font-semibold text-gray-800">{{ p.payment_id }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ p.type }}</td>
              <td class="py-4 px-4 text-sm text-gray-800">{{ p.customer_name }}</td>
              <td class="py-4 px-4 text-sm text-gray-700 truncate" style="max-width: 300px" :title="p.description">{{ p.description }}</td>
              <td class="py-4 px-4 text-sm font-bold text-green-600">Rs. {{ fmt(p.amount) }}</td>
              <td class="py-4 px-4"><StatusBadge :status="p.status" /></td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ fmtDate(p.date) }}</td>
              <td class="py-4 px-4">
                <router-link
                  v-if="p.editable && auth.can('manage_finance_ledger')"
                  :to="{ name: 'admin-manage-finance-ledger-edit', params: { id: p.id } }"
                  class="text-blue-600 hover:text-blue-800 transition"
                >
                  <i class="fas fa-edit"></i>
                </router-link>
              </td>
            </tr>
            <tr v-if="!payments.length">
              <td colspan="9" class="py-12 text-center text-gray-500">
                <i class="fas fa-credit-card fa-3x mb-3 text-gray-300"></i>
                <p class="text-lg">No payments found</p>
              </td>
            </tr>
          </tbody>
          <tfoot v-if="payments.length" class="bg-gray-50 border-t-2 border-gray-200">
            <tr>
              <td colspan="5" class="py-4 px-4 text-right text-lg font-bold text-gray-800">Total:</td>
              <td class="py-4 px-4 text-lg font-bold text-green-600">Rs. {{ fmt(totalAmount) }}</td>
              <td colspan="3"></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { getFinanceCreditLedger } from '../../api/admin';
import { fmt, fmtDate } from '../../utils/format';
import StatusBadge from '../../components/ui/StatusBadge.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const sales = ref([]);

onMounted(async () => {
  const data = await getFinanceCreditLedger();
  sales.value = data.sales;
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-book mr-3"></i>Advance Separate Finance Ledger</h1>
      <p class="text-gray-600">All advance separate finance transactions</p>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-6 card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Sale ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Customer</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Chassis No</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Credit Price</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Remaining</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Status</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Date</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="sale in sales" :key="sale.id" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-4 px-4 text-sm text-gray-800">{{ sale.id }}</td>
              <td class="py-4 px-4 text-sm font-semibold text-gray-800">{{ sale.sale_id }}</td>
              <td class="py-4 px-4 text-sm text-gray-800">{{ sale.customer_name }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ sale.chassis_no }}</td>
              <td class="py-4 px-4 text-sm font-semibold text-purple-600">Rs. {{ fmt(sale.credit_price) }}</td>
              <td class="py-4 px-4 text-sm font-bold" :class="sale.remaining_balance > 0 ? 'text-red-600' : 'text-green-600'">Rs. {{ fmt(sale.remaining_balance) }}</td>
              <td class="py-4 px-4"><StatusBadge :status="sale.status" /></td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ fmtDate(sale.sale_date) }}</td>
            </tr>
            <tr v-if="!sales.length">
              <td colspan="8" class="py-12 text-center text-gray-500">
                <i class="fas fa-book fa-3x mb-3 text-gray-300"></i>
                <p class="text-lg">No transactions found</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
